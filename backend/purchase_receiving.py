"""Receive a purchase order in separate posted supplier bills."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from workflow_extensions import retry


ORDER_ID = 'purchase_order_id'
SOURCE_VERSION = 'purchase_order_version'
LINE_INDEXES = 'purchase_order_line_indexes'
DISCOUNT_BASES = 'purchase_order_discount_bases'
STARTED = 'purchase_order_receiving_started'
RECEIPT_FIELDS = {ORDER_ID, SOURCE_VERSION, LINE_INDEXES, DISCOUNT_BASES}
OWNED_FIELDS = RECEIPT_FIELDS | {STARTED}
QUANTITY_LIMIT = Decimal('999999999999.999')


class ReceiptLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_index: int = Field(strict=True, ge=0, lt=100)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    rate: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    gst_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2, allow_inf_nan=False)
    tax_treatment: Literal['taxable', 'nil_rated', 'exempt', 'non_gst'] | None = None
    itc_treatment: Literal['pending_review', 'ineligible'] | None = None
    price_includes_tax: bool | None = Field(default=None, strict=True)
    discount_amount: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_version: int = Field(strict=True, ge=0)
    date: date
    number: str = Field(default='', max_length=16)
    due_date: date | None = None
    notes: str = Field(default='', max_length=4000)
    lines: list[ReceiptLine] = Field(min_length=1, max_length=100)
    expected_total: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)


def find_order(m, company_id, order_id, session):
    order = session.scalar(select(m.Record).where(
        m.Record.id == order_id, m.Record.company_id == company_id, m.Record.kind == 'purchase_order'))
    if not order:
        raise HTTPException(404, 'Purchase order not found')
    return order


def converted(m, order, session):
    return bool(order.data.get('vyapar_converted') or session.scalar(select(m.DocumentConversion.id).where(
        m.DocumentConversion.company_id == order.company_id, m.DocumentConversion.source_record_id == order.id)))


def receipt_rows(m, order, session):
    posted = exists().where(m.RecordPosting.company_id == order.company_id, m.RecordPosting.record_id == m.Record.id)
    return session.execute(select(m.Record, posted.label('posted')).where(
        m.Record.company_id == order.company_id, m.Record.kind == 'purchase_bill',
        m.Record.data[ORDER_ID].as_string() == order.id,
    ).order_by(m.Record.date.desc(), m.Record.number.desc(), m.Record.id.desc())).all()


def received_quantities(rows):
    received = defaultdict(Decimal)
    for receipt, posted in rows:
        if posted:
            for index, line in zip(receipt.data[LINE_INDEXES], receipt.data['lines'], strict=True):
                received[index] += Decimal(str(line['quantity']))
    return received


def reserved_discounts(m, rows, source_lines):
    used = defaultdict(Decimal)
    for receipt, posted in rows:
        if not posted:
            continue
        bases = receipt.data.get(DISCOUNT_BASES)
        for position, (index, line) in enumerate(zip(receipt.data[LINE_INDEXES], receipt.data['lines'], strict=True)):
            source = source_lines[index]
            if 'discount_amount' not in source:
                continue
            if bases is not None:
                used[index] += Decimal(str(bases[position]))
                continue
            # Older bills kept only the applied discount. Use it if it could
            # be a rounded order share; otherwise assume a supplier override.
            nominal = Decimal(str(source['discount_amount'])) * order_quantity(line['quantity']) / order_quantity(source['quantity'])
            applied = Decimal(str(line.get('discount_amount', 0)))
            used[index] += applied if abs(applied - nominal) < Decimal('0.01') else m.money(nominal)
    return used


def order_quantity(value):
    try:
        quantity = Decimal(str(value))
        if not 0 < quantity <= QUANTITY_LIMIT or quantity != quantity.quantize(Decimal('0.001')):
            raise ValueError()
    except (ValueError, ArithmeticError):
        raise HTTPException(422, 'Purchase order quantities for receiving must use up to three decimal places')
    return quantity


def order_lines(order):
    rows = order.data.get('lines')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise HTTPException(422, 'This purchase order needs 1 to 100 usable lines for partial receiving')
    for line in rows:
        if (not isinstance(line, dict) or not isinstance(line.get('description'), str)
                or not line['description'].strip() or 'quantity' not in line or 'rate' not in line):
            raise HTTPException(422, 'Some saved lines lack item, quantity or price details for partial receiving')
        order_quantity(line['quantity'])
    return rows


def review_required(detail):
    return HTTPException(409, detail, headers={'X-Apex-Error': 'PO_RECEIPT_REVIEW_REQUIRED'})


def prepare_bill(m, company, order, body, session):
    if converted(m, order, session):
        raise review_required('This purchase order was already converted to a bill')
    if body.source_version != order.data.get('version', 0):
        raise review_required('The purchase order changed. Refresh it before receiving stock')
    if not order.date <= body.date <= m.business_today():
        raise HTTPException(422, 'Bill date must be on or after the order date and no later than today')
    if body.due_date and body.due_date < body.date:
        raise HTTPException(422, 'Due date cannot be before the bill date')
    m.require_open_period(order.company_id, body.date, session)
    receipts = receipt_rows(m, order, session)
    received = received_quantities(receipts)
    source_lines = order_lines(order)
    discounts = reserved_discounts(m, receipts, source_lines)
    data = {key: order.data[key] for key in (
        'party_id', 'party_gstin', 'party_address', 'party_phone', 'place_of_supply',
        'supplier_state', 'document_discount_percent', 'round_total', 'terms',
    ) if key in order.data}
    if body.due_date:
        data['due_date'] = body.due_date.isoformat()
    data['notes'] = body.notes
    lines, indexes, discount_bases = [], [], []
    for entry in body.lines:
        index = entry.line_index
        if index in indexes or index >= len(source_lines):
            raise HTTPException(422, 'Choose each purchase order line once')
        source = source_lines[index]
        ordered = order_quantity(source['quantity'])
        after = received[index] + entry.quantity
        if after > ordered:
            raise review_required(f'Received quantity exceeds remaining quantity on order line {index + 1}')
        line = {key: source[key] for key in ('item_id', 'description', 'hsn', 'unit', 'rate', 'gst_rate',
            'discount_percent', 'tax_treatment', 'price_includes_tax', 'itc_treatment', 'mrp') if key in source}
        line['quantity'] = str(entry.quantity)
        changes = entry.model_dump(mode='json', exclude_none=True, exclude={'line_index', 'quantity', 'discount_amount'})
        line.update(changes)
        discount_basis = None
        if 'discount_amount' in source:
            discount = Decimal(str(source['discount_amount']))
            discount_basis = max(Decimal('0.00'), m.money(discount * after / ordered) - discounts[index])
        if entry.discount_amount is not None:
            line.update(discount_percent='0', discount_amount=str(entry.discount_amount))
        elif discount_basis is not None:
            line['discount_amount'] = str(discount_basis)
        lines.append(line)
        indexes.append(index)
        discount_bases.append(str(discount_basis) if discount_basis is not None else None)
    number = body.number.strip()
    if number and session.scalar(select(m.Record.id).where(
        m.Record.company_id == order.company_id, m.Record.kind == 'purchase_bill', m.Record.number == number,
    )):
        raise review_required('Purchase bill reference already exists')
    data['lines'] = lines
    m.validate_active_references(order.company_id, 'purchase_bill', order.name, data, session)
    party = m.resolve_party(order.company_id, order.name, session)
    if data.get('party_id') and (not party or data['party_id'] != party.id):
        raise HTTPException(422, 'The saved purchase order supplier no longer matches its party record')
    if party:
        data = {**{key: party.data.get(field, '') for key, field in (
            ('party_address', 'address'), ('party_gstin', 'gstin'), ('party_phone', 'phone'))}, **data, 'party_id': party.id}
    profile = session.get(m.CompanyTaxProfile, order.company_id)
    tax_mode = profile.mode if profile else 'regular'
    calculated, total = m.calculate(data, company, tax_mode, 'purchase_bill', session)
    if total <= 0:
        raise HTTPException(422, 'Purchase bill total must be greater than zero')
    return data, indexes, discount_bases, calculated, total, tax_mode


def install(app, m):
    @app.get('/api/companies/{company_id}/purchase-orders/{order_id}/receiving')
    def receiving(company_id: str, order_id: str, user=Depends(m.current_user), session: Session = Depends(m.db)):
        m.company_for(company_id, user, session)
        order = find_order(m, company_id, order_id, session)
        rows = receipt_rows(m, order, session)
        received = received_quantities(rows)
        legacy = converted(m, order, session)
        result = {'order_id': order.id, 'source_version': order.data.get('version', 0),
                  'receipts': [{'id': row.id, 'number': row.number, 'date': row.date, 'amount': str(row.amount),
                                'cancelled': not posted} for row, posted in rows]}
        if legacy:
            return {**result, 'status': 'converted', 'lines': []}
        try:
            source_lines = order_lines(order)
        except HTTPException as error:
            return {**result, 'status': 'unavailable', 'lines': [], 'reason': error.detail}
        lines = []
        for index, line in enumerate(source_lines):
            ordered = order_quantity(line['quantity'])
            lines.append({'line_index': index, 'description': line['description'], 'unit': line.get('unit', ''),
                'ordered_quantity': str(ordered), 'received_quantity': str(received[index]),
                'remaining_quantity': str(ordered - received[index]), 'rate': str(line['rate']),
                'gst_rate': str(line.get('gst_rate', '0')), 'tax_treatment': line.get('tax_treatment', 'taxable'),
                'itc_treatment': line.get('itc_treatment', 'pending_review'),
                'price_includes_tax': line.get('price_includes_tax', False),
                'discount_amount': line.get('discount_amount'), 'discount_percent': line.get('discount_percent', '0')})
        status = ('received' if all(Decimal(line['remaining_quantity']) == 0 for line in lines)
                  else 'partial' if any(received.values()) else 'open')
        return {**result, 'status': status, 'lines': lines}

    @app.post('/api/companies/{company_id}/purchase-orders/{order_id}/receipts/preview')
    def preview(company_id: str, order_id: str, body: ReceiptInput,
            user=Depends(m.current_user), session: Session = Depends(m.db)):
        company = m.company_for(company_id, user, session)
        m.require_write(company, user, session)
        order = find_order(m, company_id, order_id, session)
        _, _, _, calculated, total, tax_mode = prepare_bill(m, company, order, body, session)
        calculated = m.value_stock_lines(company_id, 'purchase_bill', calculated, tax_mode, body.date, None, session)
        return {'amount': str(total), 'data': calculated}

    @app.post('/api/companies/{company_id}/purchase-orders/{order_id}/receipts', status_code=201)
    def receive(company_id: str, order_id: str, body: ReceiptInput, request: Request,
            user=Depends(m.current_user), session: Session = Depends(m.db)):
        company = m.lock_company(company_id, user, session)
        _, digest, previous = retry(m, company_id, body, request, session, 'purchase-order-receipt:' + order_id)
        if previous:
            return previous
        if body.expected_total is None:
            raise HTTPException(422, 'Review the purchase bill total before posting the receipt')
        order = find_order(m, company_id, order_id, session)
        data, indexes, discount_bases, _, total, _ = prepare_bill(m, company, order, body, session)
        if total != body.expected_total:
            raise review_required('Purchase bill total changed. Review the updated total before posting')
        data.update({ORDER_ID: order.id, SOURCE_VERSION: body.source_version, LINE_INDEXES: indexes,
                     DISCOUNT_BASES: discount_bases})
        document = m.RecordInput(kind='purchase_bill', name=order.name, number=body.number.strip(), date=body.date, data=data)
        saved = m.save_record(company_id, document, request, user, session, commit=False, idempotency_request_hash=digest)
        order.data = {**order.data, STARTED: True}
        m.audit(session, company_id, user, 'purchase_order.received', 'purchase_order', order.id,
                {'purchase_bill_id': saved['id'], 'line_indexes': indexes})
        session.commit()
        return saved


def validate_backup(groups, indexes, posted, number, conversion_sources):
    receiving_orders = set()
    totals = defaultdict(Decimal)
    discount_totals = defaultdict(Decimal)
    records = indexes['records']
    for bill in groups['records']:
        data = bill['data']
        if not RECEIPT_FIELDS.intersection(data):
            continue
        order_id = data.get(ORDER_ID)
        order = records.get(order_id) if isinstance(order_id, str) else None
        if bill['kind'] != 'purchase_bill' or not order or order['kind'] != 'purchase_order' or order_id in conversion_sources:
            raise ValueError('Invalid purchase order receipt lineage')
        if bill['id'] not in posted and not data.get('cancelled'):
            raise ValueError('Purchase order receipt must be posted or cancelled')
        order_data = order['data']
        if (order_data.get('vyapar_converted') or data.get('source_document_id')
                or data.get(SOURCE_VERSION) != order_data.get('version', 0)
                or type(data.get(SOURCE_VERSION)) is not int
                or (order_data.get('party_id') and data.get('party_id') != order_data['party_id'])
                or bill['date'] < order['date']
                or bill['name'].strip().casefold() != order['name'].strip().casefold()):
            raise ValueError('Purchase order receipt party, version or date mismatch')
        source_lines, bill_lines, line_indexes = order_data.get('lines', []), data.get('lines', []), data.get(LINE_INDEXES)
        if (not isinstance(source_lines, list) or not isinstance(bill_lines, list)
                or not isinstance(line_indexes, list) or not 1 <= len(line_indexes) == len(bill_lines) <= 100
                or any(type(index) is not int or not 0 <= index < len(source_lines) for index in line_indexes)
                or len(set(line_indexes)) != len(line_indexes)):
            raise ValueError('Invalid purchase order receipt line indexes')
        bases = data.get(DISCOUNT_BASES)
        if DISCOUNT_BASES in data and (not isinstance(bases, list) or len(bases) != len(line_indexes)):
            raise ValueError('Invalid purchase order receipt discount bases')
        for position, (index, line) in enumerate(zip(line_indexes, bill_lines, strict=True)):
            source = source_lines[index]
            amount, ordered = number(line['quantity'], 3), number(source['quantity'], 3)
            if (line.get('item_id') != source.get('item_id') or line['description'] != source['description']
                    or not 0 < amount <= ordered):
                raise ValueError('Purchase order receipt line differs from its source')
            if bill['id'] in posted:
                totals[order_id, index] += amount
                if totals[order_id, index] > ordered:
                    raise ValueError('Purchase order received quantity exceeds ordered quantity')
            if bases is not None:
                if 'discount_amount' in source:
                    basis, fixed = number(bases[position]), number(source['discount_amount'])
                    if basis > fixed:
                        raise ValueError('Purchase order receipt discount basis exceeds original fixed discount')
                    if bill['id'] in posted:
                        discount_totals[order_id, index] += basis
                        if discount_totals[order_id, index] > fixed:
                            raise ValueError('Purchase order receipt discount bases exceed original fixed discount')
                elif bases[position] is not None:
                    raise ValueError('Purchase order receipt discount basis requires an original fixed discount')
        receiving_orders.add(order_id)
    for record in groups['records']:
        marker = record['data'].get(STARTED)
        if (marker is not None and (marker is not True or record['kind'] != 'purchase_order')
                or (marker is True) != (record['id'] in receiving_orders)):
            raise ValueError('Purchase order receipt history does not match its receiving state')
