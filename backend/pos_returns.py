"""Post a receipt-backed credit note and optional refund in one transaction."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from business_calendar import business_today
from pos_validation import requote_required
from purchase_returns import candidates, reference, verified_value
from workflow_extensions import retry


class ReturnLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_index: int = Field(ge=0, le=99, strict=True)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3, allow_inf_nan=False)


class RegisterReturn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: date
    lines: list[ReturnLine] = Field(min_length=1, max_length=100)
    return_stock: bool = Field(default=True, strict=True)
    payment_account: Literal['cash', 'bank'] | None = None
    bank_account_id: str = Field(default='default', max_length=80)
    reason: str = Field(default='', max_length=4000)
    source_version: int | None = Field(default=None, ge=0, strict=True)
    expected_total: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)


def prorate(m, total, quantity, previous_quantity, part_quantity, used):
    if previous_quantity + part_quantity == quantity:
        return total - used
    proposed = m.money(total * (previous_quantity + part_quantity) / quantity) - used
    return max(Decimal(0), min(total - used, proposed))


def prepare(m, company_id, sale_id, body, session):
    posted = select(m.RecordPosting.record_id).where(m.RecordPosting.company_id == company_id)
    sale = session.scalar(select(m.Record).where(m.Record.company_id == company_id,
        m.Record.id == sale_id, m.Record.kind == 'pos', m.Record.id.in_(posted)))
    if not sale or sale.data.get('cancelled'):
        raise HTTPException(404, 'Posted POS receipt not found')
    if body.source_version is not None and body.source_version != sale.data.get('version', 0):
        raise requote_required('Receipt changed. Reload and select the return lines again.')
    if not sale.date <= body.date <= business_today():
        raise HTTPException(422, 'Return date must be on or after the receipt date and on or before today')
    m.require_open_period(company_id, body.date, session)
    if body.payment_account == 'bank':
        m.bank_account_for(company_id, body.bank_account_id, session)
    elif body.bank_account_id not in ('', 'default'):
        raise HTTPException(422, 'Choose a bank account only for a bank refund')
    profile = session.get(m.CompanyTaxProfile, company_id)
    tax_mode = profile.mode if profile else 'regular'
    if sale.data.get('tax_mode', tax_mode) != tax_mode:
        raise HTTPException(409, 'The company tax mode changed since this sale. Review the return with your accountant.')

    originals = sale.data.get('lines', [])
    indexes = {line.source_index for line in body.lines}
    if len(indexes) != len(body.lines) or any(index >= len(originals) for index in indexes):
        raise HTTPException(422, 'Choose each receipt line once')
    previous = list(session.scalars(select(m.Record).where(m.Record.company_id == company_id,
        m.Record.kind == 'credit_note', m.Record.id.in_(posted), m.Record.data['applied_to'].as_string() == sale.id)))
    prior_lines = defaultdict(list)
    for note in previous:
        for line in note.data.get('lines', []):
            try:
                matched = candidates(line, sale)
            except HTTPException as error:
                raise HTTPException(409, 'An earlier return has an unresolved receipt line') from error
            if not indexes.intersection(matched):
                continue
            if len(matched) != 1:
                raise HTTPException(409, 'An earlier return has an ambiguous receipt line')
            prior_lines[matched[0]].append(line)

    data = {key: sale.data[key] for key in (
        'party_id', 'party_address', 'party_gstin', 'party_phone', 'shipping_address', 'place_of_supply',
        'document_discount_percent', 'round_total',
    ) if key in sale.data}
    data.update(tax_mode=tax_mode, applied_to=sale.id, return_stock=body.return_stock, pos_return=True,
                notes=body.reason.strip(), lines=[])
    supply_values = defaultdict(Decimal)
    total_base = total_tax = Decimal(0)
    for selection in body.lines:
        index, quantity = selection.source_index, selection.quantity
        original = originals[index]
        used = prior_lines[index]
        source_qty = verified_value(original, 'quantity')
        previous_qty = sum((verified_value(line, 'quantity') for line in used), Decimal(0))
        if previous_qty + quantity > source_qty:
            raise requote_required(f"Return quantity exceeds the remaining quantity for {original['description']}", status=422)
        line = {key: original[key] for key in (
            'item_id', 'description', 'hsn', 'unit', 'mrp', 'rate', 'gst_rate', 'tax_treatment',
            'price_includes_tax', 'discount_percent',
        ) if key in original}
        line.update(quantity=str(quantity), source_line_id=reference(original, index),
                    source_line_number=index + 1, source_document_id=sale.id)
        for field in ('gross', 'discount', 'document_discount', 'taxable', 'tax'):
            if field not in original and field not in ('taxable', 'tax'):
                continue
            source_total = verified_value(original, field)
            consumed = sum((verified_value(row, field) for row in used if field in row or field in ('taxable', 'tax')), Decimal(0))
            if consumed > source_total:
                raise HTTPException(409, 'An earlier return exceeds the original receipt values')
            line[field] = str(prorate(m, source_total, source_qty, previous_qty, quantity, consumed))
        if 'discount_amount' in original:
            line['discount_amount'] = line['discount']
        base, tax = Decimal(line['taxable']), Decimal(line['tax'])
        total_base += base
        total_tax += tax
        supply_values[line.get('tax_treatment', 'taxable')] += base
        data['lines'].append(line)

    tax_keys = ('cgst', 'sgst', 'igst')
    original_tax = {key: Decimal(str(sale.data.get(key, '0'))) for key in tax_keys}
    previous_tax = {key: sum((Decimal(str(row.data.get(key, '0'))) for row in previous), Decimal(0)) for key in tax_keys}
    remaining = {key: original_tax[key] - previous_tax[key] for key in tax_keys}
    if min(remaining.values()) < 0 or total_tax > sum(remaining.values()):
        raise HTTPException(409, 'Return tax exceeds the saved tax on the receipt')
    igst = min(total_tax, remaining['igst'])
    local_tax = total_tax - igst
    cgst = min(remaining['cgst'], max(local_tax - remaining['sgst'], m.money(local_tax / 2)))
    sgst = local_tax - cgst

    net = total_base + total_tax
    source_rounding = Decimal(str(sale.data.get('round_off', '0')))
    previous_rounding = sum((Decimal(str(row.data.get('round_off', '0'))) for row in previous), Decimal(0))
    source_net = sale.amount - source_rounding
    previous_net = sum((row.amount for row in previous), Decimal(0)) - previous_rounding
    if source_net <= 0 or previous_net + net > source_net:
        raise HTTPException(422, 'Return exceeds the remaining receipt value')
    sign = Decimal(-1) if source_rounding < 0 else Decimal(1)
    rounding = sign * prorate(m, abs(source_rounding), source_net, previous_net, net, sign * previous_rounding)
    amount = m.money(net + rounding)
    if amount <= 0 or amount + sum((row.amount for row in previous), Decimal(0)) > sale.amount:
        raise HTTPException(422, 'Select receipt lines with a positive remaining refundable amount')

    data.update(cgst=str(cgst), sgst=str(sgst), igst=str(igst), taxable=str(total_base), round_off=str(rounding))
    taxable_supply = supply_values['taxable']
    other_supply = sum(supply_values[key] for key in ('nil_rated', 'exempt', 'non_gst'))
    if tax_mode == 'regular':
        data['document_tax_form'] = ('bill_of_supply' if not taxable_supply else
                                     'invoice_cum_bill' if other_supply else 'tax_invoice')
    data['taxable_supply_value'] = str(taxable_supply)
    data.update({key + '_value': str(supply_values[key]) for key in ('nil_rated', 'exempt', 'non_gst')})
    return sale, data, amount


def install(app, m):
    path = '/api/companies/{company_id}/pos/{sale_id}/return'

    @app.post(path + '/preview')
    def preview(company_id: str, sale_id: str, body: RegisterReturn, user=Depends(m.current_user),
                session: Session = Depends(m.db)):
        company = m.company_for(company_id, user, session)
        m.require_write(company, user, session)
        _, data, amount = prepare(m, company_id, sale_id, body, session)
        return {'amount': str(amount), 'data': data}

    @app.post(path, status_code=201)
    def post(company_id: str, sale_id: str, body: RegisterReturn, request: Request,
             user=Depends(m.current_user), session: Session = Depends(m.db)):
        m.lock_company(company_id, user, session)
        key, digest, existing = retry(m, company_id, body, request, session, 'pos-return:' + sale_id)
        refund_key = 'pos-refund:' + sha256(key.encode()).hexdigest()
        if existing:
            refund = None
            if body.payment_account:
                child = session.scalar(select(m.IdempotencyKey).where(
                    m.IdempotencyKey.company_id == company_id, m.IdempotencyKey.key == refund_key))
                record = session.get(m.Record, child.record_id) if child else None
                if not record or record.kind != 'customer_refund' or record.data.get('credit_note_id') != existing['id']:
                    raise HTTPException(409, 'Earlier return refund requires review')
                posted = session.scalar(select(m.RecordPosting.id).where(
                    m.RecordPosting.company_id == company_id, m.RecordPosting.record_id == record.id))
                refund = {**m.obj(record), 'posted': bool(posted), 'cancelled': bool(record.data.get('cancelled'))}
            note = {**existing, 'cancelled': bool(existing['data'].get('cancelled'))}
            return {'credit_note': note, 'refund': refund}
        sale, data, amount = prepare(m, company_id, sale_id, body, session)
        if body.expected_total is not None and body.expected_total != amount:
            raise requote_required('Refund total changed. Review the updated return before paying.')
        try:
            note = m.save_record(company_id, m.RecordInput(kind='credit_note', name=sale.name, date=body.date, data=data),
                request, user, session, commit=False, idempotency_request_hash=digest, calculated_pos_return=(data, amount))
            refund = None
            if body.payment_account:
                settlement = m.RecordInput(kind='credit', date=body.date, amount=amount, data={
                    'action': 'refund', 'payment_account': body.payment_account, 'bank_account_id': body.bank_account_id,
                })
                refund = m.settle_credit_in_transaction(company_id, note['id'], settlement,
                    SimpleNamespace(headers={'Idempotency-Key': refund_key}), user, session, commit=False)
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {'credit_note': note, 'refund': refund}
