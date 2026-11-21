import hashlib
import jwt
import re
from business_calendar import financial_year_start
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from models import (
    AuditEvent, AuthSession, BankAccount, Company, CompanyMember, CompanyTaxProfile, LedgerAccount,
    NumberSeries, PaymentAllocation, PaymentSplitAllocation, PeriodLock, Record, RecordPosting,
    SECRET, StockMovement, User, engine, security,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


def db():
    from schema_readiness import schema_ready
    if not schema_ready(engine): raise HTTPException(503, 'The database migration for this release is not ready. Please try again shortly.')
    with Session(engine) as session: yield session


def current_user(credentials: HTTPAuthorizationCredentials = Depends(security), session: Session = Depends(db)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'])
        user = session.get(User, payload['sub'])
        active = session.scalar(select(AuthSession.id).where(AuthSession.id == payload['jti'], AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > datetime.now(timezone.utc))) if user else None
        if not active: raise ValueError()
        return user
    except (jwt.InvalidTokenError, KeyError, ValueError): raise HTTPException(401, 'Invalid or expired session')


def company_for(company_id: str, user: User, session: Session):
    company = session.scalar(select(Company).where(Company.id == company_id, or_(Company.owner_id == user.id, Company.id.in_(select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)))))
    if not company: raise HTTPException(404, 'Company not found')
    return company


def member_role(company: Company, user: User, session: Session):
    if company.owner_id == user.id: return 'owner'
    member = session.scalar(select(CompanyMember).where(CompanyMember.company_id == company.id, CompanyMember.user_id == user.id))
    if not member: raise HTTPException(404, 'Company not found')
    return member.role


def require_write(company: Company, user: User, session: Session):
    if member_role(company, user, session) not in {'owner', 'editor'}: raise HTTPException(403, 'This company is read only for your account')


def audit(session, company_id, user, action, entity_type, entity_id, details=None):
    session.add(AuditEvent(company_id=company_id, actor_id=user.id, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))


def audit_changes(before, after):
    """Capture changed business fields without duplicating uploaded image bytes."""
    def value(key, item):
        if key in {'image_data_url', 'image_thumbnail'}:
            return {'sha256': hashlib.sha256(str(item).encode()).hexdigest()} if item else None
        return item
    return {'changes': {key: {'before': value(key, before.get(key)), 'after': value(key, after.get(key))}
                        for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)}}


def obj(record):
    data = record.data
    if record.kind == 'purchase_bill':
        from purchase_returns import source_lines
        data = {**data, 'lines': source_lines(record)}
    return {'id': record.id, 'kind': record.kind, 'name': record.name, 'number': record.number, 'date': record.date.isoformat(), 'amount': str(record.amount), 'data': data}


def company_obj(c, session, user=None):
    profile = session.get(CompanyTaxProfile, c.id)
    return {'id': c.id, 'name': c.name, 'book_label':c.book_label, 'gstin': c.gstin, 'state_code': c.state_code, 'address': c.address, 'tax_mode': profile.mode if profile else 'regular', 'role': member_role(c, user, session) if user else 'owner'}


def lock_company(company_id, user, session):
    company = company_for(company_id, user, session)
    if session.bind.dialect.name == 'sqlite':
        # SQLite ignores SELECT FOR UPDATE. Acquire its writer lock before any
        # duplicate/capacity reads; the no-op update changes no business values.
        session.execute(Company.__table__.update().where(Company.id == company_id).values(name=Company.name))
    else:
        session.execute(select(Company.id).where(Company.id == company_id).with_for_update()).scalar_one()
    # Recheck access after waiting for the same lock used by membership changes.
    # A revoked editor must not resume a queued posting with stale authorization.
    require_write(company, user, session)
    return company


def require_open_period(company_id, date, session):
    period_lock = session.get(PeriodLock, company_id)
    if period_lock and date <= period_lock.locked_through:
        raise HTTPException(409, 'Date is in a locked accounting period')


KINDS = {'party', 'item', 'sales_invoice', 'estimate', 'proforma', 'sales_order', 'payment_in', 'credit_note', 'pos', 'purchase_bill', 'payment_out', 'expense', 'purchase_order', 'debit_note', 'bank_account', 'bank_transfer'}


DOCUMENTS = {'sales_invoice', 'estimate', 'proforma', 'sales_order', 'credit_note', 'pos', 'purchase_bill', 'purchase_order', 'debit_note', 'expense'}


POSTED_KINDS = {'sales_invoice', 'pos', 'purchase_bill', 'payment_in', 'payment_out', 'expense', 'credit_note', 'debit_note', 'bank_transfer'}


NUMBERED_KINDS = DOCUMENTS | {'payment_in', 'payment_out', 'expense', 'bank_transfer'}


DEFAULT_PREFIXES = {'sales_invoice': 'INV', 'estimate': 'EST', 'proforma': 'PF', 'sales_order': 'SO', 'payment_in': 'PIN', 'credit_note': 'CN', 'pos': 'POS', 'purchase_bill': 'BILL', 'payment_out': 'POUT', 'expense': 'EXP', 'purchase_order': 'PO', 'debit_note': 'DN', 'bank_transfer': 'TRF'}


APPLICATION_KINDS = {'payment_in': 'sales_invoice', 'credit_note': 'sales_invoice', 'payment_out': 'purchase_bill', 'debit_note': 'purchase_bill'}


SYSTEM_ACCOUNTS = {
    'cash': ('SYS-CASH', 'Cash on hand', 'asset'),
    'bank': ('SYS-BANK', 'Bank clearing', 'asset'),
    'receivable': ('SYS-AR', 'Accounts receivable', 'asset'),
    'payable': ('SYS-AP', 'Accounts payable', 'liability'),
    'customer_credits': ('SYS-CUST-CREDIT', 'Customer credit balances', 'liability'),
    'supplier_credits': ('SYS-SUPP-CREDIT', 'Supplier credit balances', 'asset'),
    'rounding': ('SYS-ROUND', 'Transaction rounding', 'expense'),
    'customer_advances': ('SYS-CUST-ADV', 'Customer advances', 'liability'),
    'unallocated_receipts': ('SYS-UNALLOC-RCPT', 'Unallocated Customer Receipts', 'liability'),
    'supplier_advances': ('SYS-SUPP-ADV', 'Supplier advances', 'asset'),
    'sales': ('SYS-SALES', 'Sales income', 'income'),
    'purchases': ('SYS-PURCHASE', 'Purchases and cost', 'expense'),
    'inventory': ('SYS-INVENTORY', 'Tracked inventory at cost', 'asset'),
    'opening_equity': ('SYS-OPENING', 'Opening balances', 'equity'),
    'inventory_gain': ('SYS-STOCK-GAIN', 'Inventory adjustment gains', 'income'),
    'inventory_loss': ('SYS-STOCK-LOSS', 'Inventory adjustment losses', 'expense'),
    'cogs': ('SYS-COGS', 'Cost of goods sold', 'expense'),
    'expenses': ('SYS-EXPENSE', 'General expenses', 'expense'),
    'output_cgst': ('SYS-OUT-CGST', 'Output CGST', 'liability'),
    'output_sgst': ('SYS-OUT-SGST', 'Output SGST', 'liability'),
    'output_igst': ('SYS-OUT-IGST', 'Output IGST', 'liability'),
    'input_cgst': ('SYS-IN-CGST', 'Input CGST pending review', 'asset'),
    'input_sgst': ('SYS-IN-SGST', 'Input SGST pending review', 'asset'),
    'input_igst': ('SYS-IN-IGST', 'Input IGST pending review', 'asset'),
}


def system_account(company_id, key, session):
    code, name, category = SYSTEM_ACCOUNTS[key]
    account = session.scalar(select(LedgerAccount).where(LedgerAccount.company_id == company_id, LedgerAccount.code == code))
    if account:
        if account.name != name or account.category != category: raise HTTPException(409, f'System account {code} has been changed')
        return account.id
    account = LedgerAccount(company_id=company_id, code=code, name=name, category=category)
    session.add(account); session.flush()
    return account.id


def bank_account_for(company_id, bank_account_id, session):
    if not bank_account_id or bank_account_id == 'default': return None
    if not isinstance(bank_account_id, str): raise HTTPException(422, 'Invalid bank account')
    account = session.scalar(select(BankAccount).where(BankAccount.company_id == company_id, BankAccount.id == bank_account_id))
    if not account: raise HTTPException(422, 'Choose a bank account in this company')
    return account


def posting_account(company_id, key, session):
    if key.startswith('bank:'):
        return bank_account_for(company_id, key[5:], session).ledger_account_id
    return system_account(company_id, key, session)


def payment_key(data):
    if data.get('payment_account', 'cash') == 'cash': return 'cash'
    bank_id = str(data.get('bank_account_id') or 'default')
    return 'bank' if bank_id == 'default' else 'bank:' + bank_id


def validate_pos_payment(company_id, data, amount, session):
    from pos_validation import validate_tender
    data = validate_tender(data, amount)
    bank_id = data.get('bank_account_id', 'default')
    if data.get('payment_account', 'cash') in ('bank', 'split'):
        bank_account_for(company_id, bank_id, session)
    elif bank_id not in (None, '', 'default'):
        raise HTTPException(422, 'Bank account can only be selected for bank payments')
    return data


def next_document_number(company_id, kind, issued, session):
    start = financial_year_start(issued)
    series = session.scalar(select(NumberSeries).where(NumberSeries.company_id == company_id, NumberSeries.kind == kind, NumberSeries.financial_year == start))
    if not series:
        series = NumberSeries(company_id=company_id, kind=kind, financial_year=start, prefix=DEFAULT_PREFIXES[kind], next_number=1)
        session.add(series); session.flush()
    year_label = f'{str(start)[-2:]}-{str(start + 1)[-2:]}'
    sequence_limit = 10 ** (9 - len(series.prefix)) - 1 if kind in ('pos', 'credit_note') else 9999
    while True:
        if series.next_number > sequence_limit: raise HTTPException(409, 'Document series is full for this year')
        number = f'{series.prefix}/{year_label}/{series.next_number:04d}'
        series.next_number += 1
        if len(number) > 16: raise HTTPException(422, 'Generated document number exceeds 16 characters')
        if not session.scalar(select(Record.id).where(Record.company_id == company_id, Record.kind == kind, Record.number == number)):
            return number


def applied_total(company_id,document_id,session,as_of=None):
    total=Decimal('0')
    for model in (PaymentAllocation,PaymentSplitAllocation):
        query=select(func.coalesce(func.sum(model.amount),0)).where(model.company_id==company_id,model.document_id==document_id)
        if as_of is not None:query=query.join(Record,Record.id==model.payment_id).where(Record.company_id==company_id,Record.date<=as_of)
        total+=Decimal(str(session.scalar(query)))
    return total


def applied_totals_by_document(company_id, session, as_of):
    """Dated settlements shared by summary and ageing, with two aggregate queries."""
    totals = {}
    for model in (PaymentAllocation, PaymentSplitAllocation):
        rows = session.execute(select(model.document_id, func.sum(model.amount))
            .join(Record, (Record.id == model.payment_id) & (Record.company_id == model.company_id))
            .where(model.company_id == company_id, Record.date <= as_of)
            .group_by(model.document_id))
        for document_id, value in rows:
            totals[document_id] = totals.get(document_id, Decimal('0')) + value
    return totals


def posting_lines(kind, amount, data, tax_mode):
    tax = {key: Decimal(str(data.get(key, '0'))) for key in ('cgst', 'sgst', 'igst')}
    pending_input = {key: Decimal(str(data.get('pending_input_' + key, tax[key]))) for key in tax}
    taxable = Decimal(str(data.get('taxable', '0')))
    stock_cost = sum((Decimal(str(line.get('inventory_cost', '0'))) for line in data.get('lines', [])), Decimal('0'))
    lines = []
    round_off = Decimal(str(data.get('round_off',0)))
    def add(key, debit=Decimal('0'), credit=Decimal('0')):
        if debit > 0 or credit > 0: lines.append((key, debit, credit))
    if kind in {'sales_invoice', 'pos', 'credit_note'}:
        reverse = kind == 'credit_note'
        credit_balance = Decimal(str(data.get('unallocated_credit', 0))) if reverse else Decimal('0')
        if kind == 'pos':
            if data.get('payment_account') == 'split':
                add('cash', debit=Decimal(data['cash_amount']))
                add(payment_key(data), debit=Decimal(data['bank_amount']))
            else:
                add(payment_key(data), debit=amount)
        else:
            add('receivable', credit=amount-credit_balance if reverse else Decimal('0'), debit=Decimal('0') if reverse else amount)
        add('customer_credits', credit=credit_balance)
        add('sales', debit=taxable if reverse else Decimal('0'), credit=Decimal('0') if reverse else taxable)
        for tax_key in tax:
            add('output_' + tax_key, debit=tax[tax_key] if reverse else Decimal('0'), credit=Decimal('0') if reverse else tax[tax_key])
        add('inventory', debit=stock_cost if reverse else Decimal('0'), credit=Decimal('0') if reverse else stock_cost)
        purchase_variance = sum((Decimal(str(line.get('return_purchase_variance', '0'))) for line in data.get('lines', [])), Decimal('0')) if reverse else Decimal('0')
        cogs_credit = stock_cost - purchase_variance
        add('cogs', debit=max(-cogs_credit, Decimal('0')) if reverse else stock_cost, credit=max(cogs_credit, Decimal('0')) if reverse else Decimal('0'))
        if reverse:
            add('purchases', debit=max(-purchase_variance, Decimal('0')), credit=max(purchase_variance, Decimal('0')))
        adjustment = round_off * (-1 if reverse else 1)
        add('rounding', debit=max(-adjustment,Decimal(0)), credit=max(adjustment,Decimal(0)))
    elif kind in {'purchase_bill', 'debit_note'}:
        reverse = kind == 'debit_note'
        credit_balance = Decimal(str(data.get('unallocated_credit', 0))) if reverse else Decimal('0')
        add('payable', debit=amount-credit_balance if reverse else Decimal('0'), credit=Decimal('0') if reverse else amount)
        add('supplier_credits', debit=credit_balance)
        purchase_cost = amount if tax_mode != 'regular' else amount - sum(pending_input.values())
        remaining_cost = purchase_cost - stock_cost - round_off
        add('inventory', debit=Decimal('0') if reverse else stock_cost, credit=stock_cost if reverse else Decimal('0'))
        signed_remaining = -remaining_cost if reverse else remaining_cost
        add('purchases', debit=max(signed_remaining, Decimal('0')), credit=max(-signed_remaining, Decimal('0')))
        adjustment = round_off * (-1 if reverse else 1)
        add('rounding', debit=max(adjustment,Decimal(0)), credit=max(-adjustment,Decimal(0)))
        if tax_mode == 'regular':
            for tax_key in tax:
                add('input_' + tax_key, debit=Decimal('0') if reverse else pending_input[tax_key], credit=pending_input[tax_key] if reverse else Decimal('0'))
    elif kind == 'payment_in':
        add(payment_key(data), debit=amount)
        advance_tax={key:Decimal(str(data.get('advance_tax',{}).get(key,0))) for key in tax} if data.get('is_advance') else {key:Decimal('0') for key in tax}
        destination = 'receivable'
        if data.get('is_advance'):
            destination = 'customer_advances'
        elif data.get('receipt_purpose') == 'unallocated':
            destination = 'unallocated_receipts'
        add(destination, credit=amount-sum(advance_tax.values()))
        for key,value in advance_tax.items():add('output_'+key,credit=value)
    elif kind == 'payment_out':
        add('supplier_advances' if data.get('is_advance') else 'payable', debit=amount); add(payment_key(data), credit=amount)
    elif kind == 'expense':
        pending = sum(pending_input.values()) if tax_mode == 'regular' else Decimal(0)
        add('expenses', debit=amount-pending-round_off); add(payment_key(data), credit=amount)
        if tax_mode == 'regular':
            for tax_key in tax: add('input_'+tax_key,debit=pending_input[tax_key])
        add('rounding',debit=max(round_off,Decimal(0)),credit=max(-round_off,Decimal(0)))
    elif kind == 'bank_transfer':
        direction=data.get('direction')
        if direction not in {'cash_to_bank','bank_to_cash','bank_to_bank'}:raise HTTPException(422,'Choose a supported transfer direction')
        source=str(data.get('bank_account_id') or 'default');bank_key='bank' if source=='default' else 'bank:'+source
        if direction=='bank_to_bank':
            destination=str(data.get('to_bank_account_id') or 'default')
            if source==destination:raise HTTPException(422,'Choose different source and destination bank accounts')
            target_key='bank' if destination=='default' else 'bank:'+destination
            add(target_key,debit=amount);add(bank_key,credit=amount)
        else:
            add(bank_key if direction=='cash_to_bank' else 'cash',debit=amount)
            add('cash' if direction=='cash_to_bank' else bank_key,credit=amount)
    if sum((debit for _, debit, _ in lines), Decimal('0')) != sum((credit for _, _, credit in lines), Decimal('0')):
        raise HTTPException(422, 'Transaction does not balance; check tax amounts')
    return lines


def money(value): return Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def normalize_document_tax_identifiers(data, purchase):
    """Validate identifier format, without inferring place-of-supply law."""
    result = dict(data)
    for field, label in (('party_gstin', 'party GSTIN'), ('place_of_supply', 'place-of-supply state code'),
                         ('supplier_state', 'supplier state code')):
        raw = data.get(field)
        value = '' if raw is None else str(raw).strip().upper()
        pattern = r'[0-9]{2}[A-Z0-9]{13}' if field == 'party_gstin' else r'[0-9]{2}'
        if value and not re.fullmatch(pattern, value):
            raise HTTPException(422, 'Enter a valid ' + label)
        result[field] = value
    if (purchase and result['party_gstin'] and result['supplier_state']
            and result['supplier_state'] != result['party_gstin'][:2]):
        raise HTTPException(422, 'Supplier state code must match the supplier GSTIN; use place of supply for the delivery state')
    return result


def source_return_itc(data, company_id, session):
    import book_services as services
    from purchase_returns import prepare
    return prepare(services, data, company_id, session)


def calculate(data, company, tax_mode, kind, session, *, exclude_return_id=None):
    import book_services as services
    purchase = kind in {'purchase_bill', 'purchase_order', 'debit_note','expense'}
    data = normalize_document_tax_identifiers(data, purchase)
    if kind == 'debit_note':
        data = source_return_itc(data, company.id, session)
    lines = data.get('lines', [])
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100: raise HTTPException(422, 'Add 1 to 100 items')
    state = str(data.get('place_of_supply', ''))
    tax_applies = tax_mode == 'regular' or purchase
    taxable = tax = pending_input_tax = Decimal('0')
    supply_values = {key: Decimal('0') for key in ('taxable', 'nil_rated', 'exempt', 'non_gst')}
    cleaned = []
    try:
        document_discount = Decimal(str(data.get('document_discount_percent', 0)))
        if not document_discount.is_finite() or not 0 <= document_discount <= 100 or document_discount.as_tuple().exponent < -2:
            raise ValueError()
    except (ValueError, TypeError, ArithmeticError):
        raise HTTPException(422, 'Document discount must be between 0 and 100 percent with at most two decimal places')
    try:
        for line in lines:
            if not isinstance(line, dict): raise ValueError()
            description = str(line.get('description', '')).strip()
            # Optional free-text item details printed under the item name (specs, serial numbers).
            details = line.get('details', '')
            if details is None: details = ''
            if not isinstance(details, str) or len(details.strip()) > 500:
                raise HTTPException(422, 'Keep item details within 500 characters')
            details = details.strip()
            hsn = str(line.get('hsn', '')).strip()
            if not hsn and isinstance(line.get('item_id'), str):
                # A linked item's HSN/SAC is authoritative when the client left it blank (statutory invoice field).
                linked = session.scalar(select(Record).where(Record.company_id == company.id, Record.id == line['item_id'], Record.kind == 'item'))
                hsn = str(linked.data.get('hsn', '')).strip() if linked else ''
            if not description or len(description) > 200 or len(hsn) > 16: raise ValueError()
            qty, rate, gst = Decimal(str(line['quantity'])), Decimal(str(line['rate'])), Decimal(str(line.get('gst_rate', 0)))
            discount_percent = Decimal(str(line.get('discount_percent', 0)))
            if line.get('mrp') not in (None, ''):
                mrp = Decimal(str(line['mrp']))
                if not mrp.is_finite() or mrp < 0 or mrp > Decimal('9999999999999.99') or mrp.as_tuple().exponent < -2: raise ValueError()
            if len(str(line.get('unit', ''))) > 24: raise ValueError()
            if qty <= 0 or rate < 0 or gst < 0 or gst > 100 or discount_percent < 0 or discount_percent > 100 or discount_percent.as_tuple().exponent < -2: raise ValueError()
            if not all(value.is_finite() for value in (qty, rate, gst, discount_percent)): raise ValueError()
            item_id = line.get('item_id')
            if item_id:
                if not isinstance(item_id, str) or len(item_id) > 80: raise HTTPException(422, 'Invalid item selection')
                item = session.scalar(select(Record).where(Record.id == item_id, Record.company_id == company.id, Record.kind == 'item'))
                if not item or item.name.casefold() != description.casefold(): raise HTTPException(422, 'Choose an item from this company and keep its name')
                if item.data.get('track_stock') and (qty.as_tuple().exponent < -3 or qty > Decimal('999999999999.999')):
                    raise HTTPException(422, 'Tracked stock quantity must have at most three decimal places')
            else:
                named_items = master_name_matches(company.id, 'item', description, session)
                if any(item.data.get('track_stock') for item in named_items):
                    raise HTTPException(422, 'Choose the tracked item from this company to post stock')
            if not tax_applies and gst != 0: raise HTTPException(422, 'Non-GST sales cannot charge GST')
            treatment = line.get('tax_treatment', 'taxable')
            if treatment not in supply_values:
                raise HTTPException(422, 'Choose taxable, nil rated, exempt or non-GST treatment')
            if treatment != 'taxable' and gst != 0:
                raise HTTPException(422, 'Nil rated, exempt and non-GST lines cannot charge GST')
            if tax_mode == 'regular' and not purchase and treatment == 'taxable' and gst == 0:
                raise HTTPException(422, 'Classify zero-rate outward supplies as nil rated, exempt or non-GST')
            itc_treatment = line.get('itc_treatment', 'pending_review') if purchase and tax_mode == 'regular' else 'ineligible'
            if itc_treatment not in {'pending_review', 'ineligible'}:
                raise HTTPException(422, 'Choose whether supplier GST is pending input-credit review or ineligible')
            inclusive=line.get('price_includes_tax',False)
            if not isinstance(inclusive,bool):raise ValueError()
            gross = money(qty * rate); discount = money(gross * discount_percent / 100)
            if 'discount_amount' in line:
                fixed_discount = Decimal(str(line['discount_amount']))
                if not fixed_discount.is_finite() or fixed_discount < 0 or fixed_discount > gross or fixed_discount.as_tuple().exponent < -2 or discount_percent:
                    raise ValueError()
                discount = fixed_discount
            document_discount_value=money((gross-discount)*document_discount/100)
            net=gross-discount-document_discount_value
            base=money(net/(1+gst/100)) if inclusive else net
            line_tax=net-base if inclusive else money(base*gst/100)
            taxable += base; tax += line_tax
            supply_values[treatment] += base
            if itc_treatment == 'pending_review': pending_input_tax += line_tax
            # Valuation is derived from stock movements, never accepted from a client.
            line = {key: value for key, value in line.items() if key not in {'inventory_cost', 'legacy_shortage_cost', 'shortage_cost', 'shortage_quantity', 'stock_cost_provisional', 'return_cost_basis', 'return_purchase_variance', 'return_cost_reconciliation'}}
            line = {key: value for key, value in line.items() if key not in {'remaining_return_quantity', 'return_capacity_reason', 'return_capacity_scope'}}
            if kind != 'debit_note': line = {key: value for key, value in line.items() if key not in {'source_line_id', 'source_document_id', 'source_line_number'}}
            line = {key: value for key, value in line.items() if key != 'details'}
            if details: line['details'] = details
            cleaned.append({**line, 'description': description, 'hsn': hsn, 'gross': str(gross),
                            'discount_percent': str(discount_percent), 'discount': str(discount),'document_discount':str(document_discount_value),
                            'taxable': str(base), 'tax': str(line_tax), 'itc_treatment': itc_treatment,
                            'tax_treatment': treatment})
    except (ValueError, TypeError, KeyError, ArithmeticError, InvalidOperation): raise HTTPException(422, 'Invalid item details, quantity, rate or GST rate')
    if taxable + tax > Decimal('9999999999999.99'): raise HTTPException(422, 'Document amount exceeds supported range')
    if tax_mode == 'regular' and (not company.state_code or not state): raise HTTPException(422, 'Company state code and place of supply are required for GST')
    if tax_mode == 'composition' and kind in {'sales_invoice', 'estimate', 'proforma', 'sales_order', 'credit_note', 'pos'} and state != company.state_code:
        raise HTTPException(422, 'Composition outward supplies must use the company state')
    if tax_mode == 'regular' and data.get('party_gstin') and kind in {'sales_invoice', 'pos', 'credit_note'} and supply_values['taxable'] > 0 and sum((supply_values[key] for key in ('nil_rated', 'exempt', 'non_gst')), Decimal('0')) > 0:
        raise HTTPException(422, 'Issue separate taxable and non-taxable outward documents in this workflow')
    origin_state = str(data.get('supplier_state') or str(data.get('party_gstin') or '')[:2] or company.state_code) if purchase else company.state_code
    if origin_state and not re.fullmatch(r'\d{2}',origin_state):raise HTTPException(422,'Enter a valid supplier state')
    if purchase: data = {**data, 'supplier_state': origin_state}
    unclassified_supplier_tax = tax_mode != 'regular' and purchase and tax > 0 and (not origin_state or not state)
    intra = tax_applies and origin_state == state and not unclassified_supplier_tax
    cgst = money(tax / 2) if intra else Decimal('0')
    pending_cgst = money(pending_input_tax / 2) if intra else Decimal('0')
    data = {**data, 'tax_mode': tax_mode, 'lines': cleaned, 'taxable': str(taxable),
            'taxable_supply_value': str(supply_values['taxable']), 'nil_rated_value': str(supply_values['nil_rated']),
            'exempt_value': str(supply_values['exempt']), 'non_gst_value': str(supply_values['non_gst']),
            'document_tax_form': 'bill_of_supply' if tax_mode == 'regular' and supply_values['taxable'] == 0 else 'invoice_cum_bill' if tax_mode == 'regular' and supply_values['taxable'] > 0 and sum(supply_values[k] for k in ('nil_rated','exempt','non_gst')) > 0 else 'tax_invoice',
            'cgst': str(cgst), 'sgst': str(tax - cgst if intra else Decimal('0')), 'igst': str(Decimal('0') if intra or unclassified_supplier_tax else tax), 'supplier_tax': str(tax if unclassified_supplier_tax else Decimal('0')),
            'pending_input_cgst': str(pending_cgst), 'pending_input_sgst': str(pending_input_tax - pending_cgst if intra else Decimal('0')),
            'pending_input_igst': str(pending_input_tax if not intra and not unclassified_supplier_tax else Decimal('0')),
            'input_tax_ineligible': str(tax - pending_input_tax if purchase else Decimal('0'))}
    if kind == 'debit_note':
        from purchase_returns import reconcile_tax
        data = reconcile_tax(services, data, company.id, session, exclude_return_id)
        taxable = Decimal(data['taxable'])
        tax = sum((Decimal(data[key]) for key in ('cgst', 'sgst', 'igst', 'supplier_tax')), Decimal(0))
    total=money(taxable+tax)
    if data.get('round_total') not in (None,False,True):raise HTTPException(422,'Invalid rounding option')
    rounded=total.quantize(Decimal('1'),rounding=ROUND_HALF_UP) if data.get('round_total') else total
    if rounded > Decimal('9999999999999.99'): raise HTTPException(422, 'Rounded document amount exceeds supported range')
    data={**data,'round_off':str(rounded-total)}
    return data, money(rounded)


def value_stock_lines(company_id, kind, data, tax_mode, issued, target, session):
    import book_services as services
    if kind not in {'purchase_bill', 'debit_note', 'sales_invoice', 'pos', 'credit_note'}: return data
    if kind in {'credit_note','debit_note'} and data.get('return_stock') is False:
        return {**data,'lines':[{**line,'inventory_cost':'0'} for line in data.get('lines',[])]}
    states = {}
    last_unit_costs = {}
    def receipt_cost(qty, basis, held_qty, held_value):
        if held_qty >= 0: return basis
        if held_value > 0: raise HTTPException(409, 'Negative stock has an inconsistent positive value; review its valuation')
        covered = min(qty, -held_qty)
        # Retire the negative inventory's carrying cost; price differences go
        # through the purchase/return posting, never remain on zero units.
        released = -held_value if covered == -held_qty else money(-held_value * covered / -held_qty)
        return basis - money(basis * covered / qty) + released
    previous_notes = {}
    previous_purchase_variance = {}
    if target and kind in {'credit_note', 'debit_note'}:
        posted_notes = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
        for note in session.scalars(select(Record).where(Record.company_id == company_id, Record.kind.in_([kind, 'stock_return'] if kind == 'credit_note' else [kind]), or_(Record.id.in_(posted_notes), (Record.kind == 'stock_return') & Record.id.in_(select(StockMovement.source_record_id).where(StockMovement.company_id == company_id))))):
            if note.data.get('applied_to') != target.id or note.data.get('return_stock') is False: continue
            for line in note.data.get('lines', []):
                item_id = line.get('item_id')
                if item_id:
                    if 'inventory_cost' not in line:
                        raise HTTPException(409, 'Older stock return has no valuation; migrate it before posting')
                    previous_purchase_variance[item_id] = previous_purchase_variance.get(item_id, Decimal('0')) + Decimal(str(line.get('return_purchase_variance', '0')))
                    qty, cost = previous_notes.get(item_id, (Decimal('0'), Decimal('0')))
                    previous_notes[item_id] = (qty + Decimal(str(line['quantity'])),
                                               cost + Decimal(str(line.get('return_cost_basis', line.get('inventory_cost', '0')))))
    valued = []
    returned_here = {}
    for line in data.get('lines', []):
        line = dict(line)
        item_id = line.get('item_id')
        item = session.get(Record, item_id) if item_id else None
        if not item or not item.data.get('track_stock'):
            valued.append(line); continue
        if item_id not in states:
            movements = list(session.scalars(select(StockMovement).where(
                StockMovement.company_id == company_id, StockMovement.item_id == item_id).order_by(StockMovement.date, StockMovement.id)))
            if any(m.cost_value is None for m in movements):
                raise HTTPException(409, f'{item.name} has older unvalued stock movements; migrate them before posting')
            if movements and movements[-1].date > issued:
                raise HTTPException(409, f'Post tracked stock for {item.name} on or after {movements[-1].date}')
            states[item_id] = [sum((m.quantity for m in movements), Decimal('0')),
                               sum((m.cost_value for m in movements), Decimal('0'))]
            last_unit_costs[item_id] = Decimal('0')
            for movement in reversed(movements):
                if movement.quantity <= 0: continue
                source = session.get(Record, movement.source_record_id)
                source_lines = source.data.get('lines', []) if source else []
                original = source_lines[movement.line_index] if movement.line_index < len(source_lines) else {}
                basis = Decimal(str(original.get('return_cost_basis', movement.cost_value)))
                if source and source.kind == 'purchase_bill':
                    basis += Decimal(str(original.get('shortage_cost', original.get('legacy_shortage_cost', '0'))))
                if basis > 0:
                    last_unit_costs[item_id] = basis / movement.quantity
                    break
        held_qty, held_value = states[item_id]
        qty = Decimal(str(line['quantity']))
        if kind in {'credit_note', 'debit_note'}:
            source_lines = [original for original in target.data.get('lines', []) if original.get('item_id') == item_id]
            if not source_lines: raise HTTPException(422, f'{item.name} is not linked to the source document')
            if kind == 'credit_note' and any('inventory_cost' not in original for original in source_lines):
                raise HTTPException(409, f'{item.name} source sale has no valuation; migrate it before returning stock')
            source_qty = sum((Decimal(str(original['quantity'])) for original in source_lines), Decimal('0'))
            prior_qty, prior_cost = previous_notes.get(item_id, (Decimal('0'), Decimal('0')))
            now_qty = returned_here.get(item_id, Decimal('0')) + qty
            if prior_qty + now_qty > source_qty:
                raise HTTPException(422, f'{item.name} return quantity exceeds the source document')
            returned_here[item_id] = now_qty
        if kind == 'purchase_bill':
            cost = money(Decimal(str(line['taxable'])) + (Decimal(str(line['tax'])) if tax_mode != 'regular' or line.get('itc_treatment') == 'ineligible' else Decimal('0')))
            if held_qty < 0:
                inventory = receipt_cost(qty, cost, held_qty, held_value)
                line['shortage_cost'] = str(cost - inventory)
                if item.data.get('vyapar_stock_migrated'): line['legacy_shortage_cost'] = line['shortage_cost']
                cost = inventory
            held_qty += qty; held_value += cost
        elif kind == 'credit_note':
            source_cost = sum((Decimal(str(original.get('inventory_cost', '0'))) for original in source_lines), Decimal('0'))
            purchase_variance = Decimal('0')
            if any(original.get('stock_cost_provisional') or Decimal(str(original.get('shortage_quantity', '0'))) > 0 for original in source_lines):
                from inventory_reconciliation import reconciled_source_cost
                source_cost, purchase_variance, evidence = reconciled_source_cost(services, company_id, item_id, target, session)
                line['return_cost_reconciliation'] = evidence
            remaining_qty = source_qty - prior_qty - (now_qty - qty)
            # Keep nominal returned cost separate from inventory absorbed by
            # another sale's deficit, so partial returns cannot consume it twice.
            remaining_cost = source_cost - prior_cost - sum((Decimal(str(other.get('return_cost_basis', other.get('inventory_cost', '0')))) for other in valued if other.get('item_id') == item_id), Decimal('0'))
            if remaining_cost < 0: raise HTTPException(409, 'Prior returns exceed source cost; review historical valuation')
            cost = remaining_cost if qty == remaining_qty else min(remaining_cost, money(source_cost * qty / source_qty))
            returned_variance = previous_purchase_variance.get(item_id, Decimal('0')) + sum((Decimal(str(other.get('return_purchase_variance', '0'))) for other in valued if other.get('item_id') == item_id), Decimal('0'))
            remaining_variance = purchase_variance - returned_variance
            proposed_variance = money(purchase_variance * qty / source_qty)
            allocated_variance = min(max(proposed_variance, min(remaining_variance, Decimal('0'))), max(remaining_variance, Decimal('0')))
            line['return_purchase_variance'] = str(remaining_variance if qty == remaining_qty else allocated_variance)
            line['return_cost_basis'] = str(cost)
            cost = receipt_cost(qty, cost, held_qty, held_value)
            held_qty += qty; held_value += cost
        else:
            if (kind == 'debit_note' or kind == 'pos' and data.get('require_available_stock')) and qty > held_qty:
                if kind == 'pos':
                    from pos_validation import requote_required
                    raise requote_required(f'Insufficient stock for {item.name}', status=422)
                raise HTTPException(422, f'Insufficient stock for {item.name}')
            if hasattr(services, 'commerce_assert_available'):
                services.commerce_assert_available(company_id, item_id, qty, held_qty, session)
            unit_cost = held_value / held_qty if held_qty != 0 else last_unit_costs[item_id]
            if unit_cost < 0: raise HTTPException(409, f'Inconsistent stock valuation for {item.name}')
            cost = held_value if qty == held_qty else money(unit_cost * qty)
            if kind in {'sales_invoice', 'pos'} and qty > max(held_qty, Decimal('0')):
                line['shortage_quantity'] = str(qty - max(held_qty, Decimal('0')))
                line['stock_cost_provisional'] = True
            held_qty -= qty; held_value -= cost
        states[item_id] = [held_qty, held_value]
        line['inventory_cost'] = str(cost)
        valued.append(line)
    return {**data, 'lines': valued}


def master_name_matches(company_id, kind, name, session):
    # Python casefold is shared with imports/statements; SQL lower differs by DB
    # and does not implement the same Unicode identity policy.
    key = name.strip().casefold()
    return [row for row in session.scalars(select(Record).where(
        Record.company_id == company_id, Record.kind == kind))
        if row.name.strip().casefold() == key]
