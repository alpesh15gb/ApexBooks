import hashlib
import json
from accounting import (
    audit, company_for, current_user, db, lock_company, money, obj, require_open_period,
    system_account,
)
from business_calendar import business_today
from datetime import date as DateType, datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from models import IdempotencyKey, Journal, JournalLine, Record, RecordPosting, StockMovement, User
from schemas import OpeningStockInput, StockAdjustmentInput, StockCountInput
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


router = APIRouter()


@router.post('/api/companies/{company_id}/stock/opening', status_code=201)
def post_opening_stock(company_id: str, body: OpeningStockInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    import book_services as services
    lock_company(company_id, user, session)
    retry_key = request.headers.get('Idempotency-Key', '').strip()
    if retry_key:
        from workflow_extensions import retry
        retry_key, request_digest, previous = retry(services, company_id, body, request, session, 'stock-opening')
        if previous: return previous
    require_open_period(company_id, body.date, session)
    item = session.scalar(select(Record).where(Record.company_id == company_id,
        Record.id == body.item_id, Record.kind == 'item'))
    if not item or not item.data.get('track_stock'):
        raise HTTPException(422, 'Choose a stock-tracked item in this company')
    if item.data.get('item_type','goods') != 'goods':raise HTTPException(422,'Opening inventory is supported for goods only; review this legacy service item without changing existing books')
    if item.data.get('is_active',True) is False:raise HTTPException(422,'Reactivate this item before posting opening stock')
    if session.scalar(select(StockMovement.id).where(StockMovement.company_id == company_id,
        StockMovement.item_id == item.id)):
        raise HTTPException(409, 'Opening stock must be posted before other movements for this item')
    amount = money(body.quantity * body.unit_cost)
    if amount <= 0 or amount > Decimal('9999999999999.99'):
        raise HTTPException(422, 'Opening stock value is outside the supported range')
    record = Record(company_id=company_id, kind='stock_opening', name=item.name, date=body.date,
        amount=amount, data={'item_id': item.id, 'quantity': str(body.quantity),
                             'unit_cost': str(body.unit_cost), 'unit': item.data.get('unit', '')})
    session.add(record)
    try:
        session.flush()
        record.number = 'OPEN-' + record.id[:8].upper()
        journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + record.id,
                          memo=f'Opening stock {item.name}', created_by=user.id)
        session.add(journal); session.flush()
        session.add(JournalLine(company_id=company_id, journal_id=journal.id,
            account_id=system_account(company_id, 'inventory', session), debit=amount, credit=Decimal('0')))
        session.add(JournalLine(company_id=company_id, journal_id=journal.id,
            account_id=system_account(company_id, 'opening_equity', session), debit=Decimal('0'), credit=amount))
        session.add(RecordPosting(company_id=company_id, record_id=record.id, journal_id=journal.id))
        session.add(StockMovement(company_id=company_id, item_id=item.id, source_record_id=record.id,
                                  line_index=0, date=body.date, quantity=body.quantity, cost_value=amount))
        audit(session, company_id, user, 'stock.opening_posted', 'item', item.id,
              {'quantity': str(body.quantity), 'value': str(amount), 'record_id': record.id})
        if hasattr(services, 'commerce_stock_changed'): services.commerce_stock_changed(company_id, session)
        if retry_key:
            session.add(IdempotencyKey(company_id=company_id, key=retry_key, request_hash=request_digest, record_id=record.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Opening stock conflicts with an existing entry')
    return {**obj(record), 'posted': True}


@router.post('/api/companies/{company_id}/stock/adjustments', status_code=201)
def post_stock_adjustment(company_id: str, body: StockAdjustmentInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    import book_services as services
    lock_company(company_id, user, session)
    retry_key = request.headers.get('Idempotency-Key', '').strip()
    if retry_key:
        from workflow_extensions import retry
        retry_key, request_digest, previous = retry(services, company_id, body, request, session, 'stock-adjustment')
        if previous: return previous
    else:
        request_digest = None
    require_open_period(company_id, body.date, session)
    if body.direction not in {'increase', 'decrease'} or not body.reason.strip():
        raise HTTPException(422, 'Choose an adjustment direction and provide a reason')
    if (body.direction == 'increase') != (body.unit_cost is not None):
        raise HTTPException(422, 'Unit cost is required only when adding stock')
    item, movements = adjustment_stock(company_id, body.item_id, session)
    return post_adjustment(company_id, body, item, movements, user, session, retry_key, request_digest)


def adjustment_stock(company_id, item_id, session):
    item = session.scalar(select(Record).where(Record.company_id == company_id,
        Record.id == item_id, Record.kind == 'item'))
    if not item or not item.data.get('track_stock'):
        raise HTTPException(422, 'Choose a stock-tracked item in this company')
    movements = list(session.scalars(select(StockMovement).where(
        StockMovement.company_id == company_id, StockMovement.item_id == item.id
    ).order_by(StockMovement.date, StockMovement.id)))
    return item, movements


def count_snapshot(company_id, item, date, movements):
    history = [(m.id, m.date.isoformat(), str(m.quantity), str(m.cost_value)) for m in movements]
    return hashlib.sha256(json.dumps([company_id, item.id, date.isoformat(), history]).encode()).hexdigest()


def validate_count_stock(item, date, movements):
    if item.data.get('item_type', 'goods') != 'goods':
        raise HTTPException(422, 'Physical stock counts require goods')
    if movements and movements[-1].date > date:
        raise HTTPException(409, 'A future-dated movement exists. Review it before counting this item')
    on_hand = sum((m.quantity for m in movements), Decimal('0'))
    if on_hand < 0:
        raise HTTPException(409, 'Reconcile negative stock with a purchase bill or linked return before counting')
    if on_hand > Decimal('999999999999.999'):
        raise HTTPException(409, 'On-hand stock exceeds the supported range for a physical count')
    if any(m.cost_value is None for m in movements):
        raise HTTPException(409, f'{item.name} has older unvalued stock movements; migrate them before counting')
    return on_hand


@router.get('/api/companies/{company_id}/stock/counts/{item_id}')
def get_stock_count(company_id: str, item_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    date = business_today()
    item, movements = adjustment_stock(company_id, item_id, session)
    on_hand = validate_count_stock(item, date, movements)
    return {'item_id': item.id, 'date': date, 'on_hand': str(on_hand),
            'stock_snapshot': count_snapshot(company_id, item, date, movements)}


@router.post('/api/companies/{company_id}/stock/counts', status_code=201)
def post_stock_count(company_id: str, body: StockCountInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    import book_services as services
    from workflow_extensions import retry

    lock_company(company_id, user, session)
    retry_key, request_digest, previous = retry(services, company_id, body, request, session, 'stock-count')
    if previous:
        if previous['data'].get('quantity_only') is True:
            previous['stock_posted'] = True
        return previous
    if body.date != business_today():
        raise HTTPException(409, 'The business date changed. Refresh on-hand stock and count again')
    require_open_period(company_id, body.date, session)
    item, movements = adjustment_stock(company_id, body.item_id, session)
    if body.stock_snapshot != count_snapshot(company_id, item, body.date, movements):
        raise HTTPException(409, 'Stock moved after this count started. Refresh on-hand stock and count again')
    on_hand = validate_count_stock(item, body.date, movements)
    difference = body.counted_quantity - on_hand
    if not difference:
        raise HTTPException(422, 'Count matches on-hand stock. No adjustment is needed')
    if not body.reason.strip():
        raise HTTPException(422, 'Provide a reason for the count difference')
    if (difference > 0) != (body.unit_cost is not None):
        raise HTTPException(422, 'Unit cost is required only when adding stock')
    adjustment = StockAdjustmentInput(item_id=item.id, date=body.date, direction='increase' if difference > 0 else 'decrease',
        quantity=abs(difference), unit_cost=body.unit_cost, reason=body.reason)
    return post_adjustment(company_id, adjustment, item, movements, user, session, retry_key, request_digest,
        count={'on_hand_before': str(on_hand), 'counted_quantity': str(body.counted_quantity)})


def post_adjustment(company_id, body, item, movements, user, session, retry_key, request_digest, *, count=None):
    import book_services as services
    if any(m.cost_value is None for m in movements):
        raise HTTPException(409, f'{item.name} has older unvalued stock movements; migrate them before adjusting')
    if movements and body.date < movements[-1].date:
        raise HTTPException(409, 'Stock adjustments cannot be backdated before the last movement')
    held_qty = sum((m.quantity for m in movements), Decimal('0'))
    held_value = sum((m.cost_value for m in movements), Decimal('0'))
    quantity_only = count is not None and body.direction == 'decrease' and held_value == 0
    if body.direction == 'decrease':
        if body.quantity > held_qty:
            raise HTTPException(422, f'Insufficient stock for {item.name}')
        if hasattr(services, 'commerce_assert_available'):
            services.commerce_assert_available(company_id, item.id, body.quantity, held_qty, session)
        amount = held_value if body.quantity == held_qty else money(held_value * body.quantity / held_qty)
        quantity, cost_value = -body.quantity, -amount
        debit_key, credit_key = 'inventory_loss', 'inventory'
    else:
        if held_qty < 0: raise HTTPException(409, 'Replenish negative legacy stock with a purchase bill or a return against its original invoice')
        if held_qty + body.quantity > Decimal('999999999999.999'):
            raise HTTPException(422, 'Stock quantity exceeds the supported range')
        amount = money(body.quantity * body.unit_cost)
        quantity, cost_value = body.quantity, amount
        debit_key, credit_key = 'inventory', 'inventory_gain'
    if (amount <= 0 and not quantity_only) or amount > Decimal('9999999999999.99'):
        raise HTTPException(422, 'Adjustment value is outside the supported range')
    data = {'item_id': item.id, 'direction': body.direction,
        'quantity': str(body.quantity), 'cost_value': str(amount),
        'unit_cost': str(body.unit_cost) if body.unit_cost is not None else None,
        'reason': body.reason.strip(), 'unit': item.data.get('unit', ''),
        'created_at': datetime.now(timezone.utc).isoformat()}
    if count is not None:
        data['stock_count'] = count
    if quantity_only:
        data['quantity_only'] = True
    record = Record(company_id=company_id, kind='stock_adjustment', name=item.name, date=body.date,
        amount=amount, data=data)
    session.add(record)
    try:
        session.flush()
        record.number = 'ADJ-' + record.id[:8].upper()
        if not quantity_only:
            journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + record.id,
                              memo=f'Stock {body.direction}: {item.name} — {body.reason.strip()}'[:500], created_by=user.id)
            session.add(journal); session.flush()
            session.add(JournalLine(company_id=company_id, journal_id=journal.id,
                account_id=system_account(company_id, debit_key, session), debit=amount, credit=Decimal('0')))
            session.add(JournalLine(company_id=company_id, journal_id=journal.id,
                account_id=system_account(company_id, credit_key, session), debit=Decimal('0'), credit=amount))
            session.add(RecordPosting(company_id=company_id, record_id=record.id, journal_id=journal.id))
        session.add(StockMovement(company_id=company_id, item_id=item.id, source_record_id=record.id,
                                  line_index=0, date=body.date, quantity=quantity, cost_value=cost_value))
        audit_data = {'direction': body.direction, 'quantity': str(body.quantity),
            'value': str(amount), 'record_id': record.id}
        if count is not None:
            audit_data['stock_count'] = count
        if quantity_only:
            audit_data['quantity_only'] = True
        audit(session, company_id, user, 'stock.adjustment_posted', 'item', item.id, audit_data)
        if hasattr(services, 'commerce_stock_changed'): services.commerce_stock_changed(company_id, session)
        if retry_key:
            session.add(IdempotencyKey(company_id=company_id, key=retry_key, request_hash=request_digest, record_id=record.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Stock adjustment conflicts with an existing entry')
    if quantity_only:
        return {**obj(record), 'posted': False, 'stock_posted': True}
    return {**obj(record), 'posted': True}


@router.get('/api/companies/{company_id}/reports/items')
def item_report(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    kinds = {'sales_invoice', 'pos', 'credit_note', 'purchase_bill', 'debit_note'}
    records = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.kind.in_(kinds), Record.date <= to_date)))
    values = {}
    for record in records:
        for line in record.data.get('lines', []):
            name = str(line.get('description', '')).strip()
            if not name: continue
            key = (name.casefold(), str(line.get('hsn', '')).strip())
            if key not in values:
                values[key] = {'name': name, 'hsn': key[1], 'opening_quantity': Decimal('0'), 'purchased_quantity': Decimal('0'),
                               'sold_quantity': Decimal('0'), 'closing_quantity': Decimal('0'), 'purchase_value': Decimal('0'), 'sales_value': Decimal('0')}
            item = values[key]
            qty = Decimal(str(line.get('quantity', 0))) if record.data.get('return_stock') is not False else Decimal('0')
            taxable = Decimal(str(line.get('taxable', 0)))
            movement = qty if record.kind in {'purchase_bill', 'credit_note'} else -qty
            # These legacy quantity keys represent document movement, not stock on hand.
            # Stock introductions and adjustments are intentionally in the tracked-stock report.
            if record.date < from_date:
                item['opening_quantity'] += movement
            else:
                if record.kind == 'purchase_bill':
                    item['purchased_quantity'] += qty; item['purchase_value'] += taxable
                elif record.kind == 'debit_note':
                    item['purchased_quantity'] -= qty; item['purchase_value'] -= taxable
                elif record.kind in {'sales_invoice', 'pos'}:
                    item['sold_quantity'] += qty; item['sales_value'] += taxable
                else:
                    item['sold_quantity'] -= qty; item['sales_value'] -= taxable
            item['closing_quantity'] += movement
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
            'quantity_basis':'purchase_sales_documents_only',
            'quantity_note':'Document movement only; excludes stock introductions and adjustments. Use tracked stock for on-hand quantities.',
            'rows': [{**item, **{field: str(item[field]) for field in ('opening_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity', 'purchase_value', 'sales_value')}}
                     for item in sorted(values.values(), key=lambda row: (row['name'].casefold(), row['hsn']))]}


@router.get('/api/companies/{company_id}/reports/items.{fmt}')
def export_items(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    from routers.reports import export_table
    company = company_for(company_id, user, session)
    data = item_report(company_id, from_date, to_date, user, session)
    keys = ('name', 'hsn', 'opening_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity', 'purchase_value', 'sales_value')
    rows = [[row[key] for key in keys] for row in data['rows']]
    return export_table(company.name, f"Purchase/sales document movement {from_date} to {to_date}", ['Item', 'HSN/SAC', 'Net before period', 'Purchased net', 'Sold net', 'Net through end date', 'Purchase value', 'Sales value'], rows, fmt, 'item-activity')


@router.get('/api/companies/{company_id}/pos/stock')
def pos_stock_summary(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    day = business_today()
    totals = select(StockMovement.item_id, func.sum(StockMovement.quantity).label('quantity')).where(
        StockMovement.company_id == company_id, StockMovement.date <= day,
    ).group_by(StockMovement.item_id).subquery()
    query = select(Record.id, func.coalesce(totals.c.quantity, 0)).outerjoin(totals, totals.c.item_id == Record.id).where(
        Record.company_id == company_id, Record.kind == 'item', Record.data['track_stock'].as_boolean().is_(True),
    ).order_by(Record.id)
    return {'date': day, 'rows': [{'item_id': item_id, 'closing_quantity': str(quantity)}
            for item_id, quantity in session.execute(query)]}


@router.get('/api/companies/{company_id}/reports/stock')
def stock_report(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    items = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.kind == 'item')))
    values = {item.id: {'item_id': item.id, 'name': item.name, 'unit': item.data.get('unit', ''),
        'opening_quantity': Decimal('0'), 'introduced_quantity': Decimal('0'), 'adjustment_quantity': Decimal('0'), 'purchased_quantity': Decimal('0'), 'sold_quantity': Decimal('0'),
        'closing_quantity': Decimal('0'), 'closing_value': Decimal('0'), 'unvalued_movements': 0}
        for item in items if item.data.get('track_stock')}
    movements = session.scalars(select(StockMovement).where(StockMovement.company_id == company_id,
        StockMovement.date <= to_date).order_by(StockMovement.date, StockMovement.id))
    for movement in movements:
        row = values.get(movement.item_id)
        if row is None: continue
        if movement.cost_value is None: row['unvalued_movements'] += 1
        else: row['closing_value'] += movement.cost_value
        if movement.date < from_date: row['opening_quantity'] += movement.quantity
        else:
            source = session.get(Record, movement.source_record_id)
            if source.kind == 'stock_opening': row['introduced_quantity'] += movement.quantity
            elif source.kind == 'stock_adjustment': row['adjustment_quantity'] += movement.quantity
            elif source.kind in {'purchase_bill', 'debit_note'}: row['purchased_quantity'] += movement.quantity
            else: row['sold_quantity'] -= movement.quantity
        row['closing_quantity'] += movement.quantity
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
        'rows': [{**row, **{key: str(row[key]) for key in ('opening_quantity', 'introduced_quantity', 'adjustment_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity')},
                  'closing_value': None if row['unvalued_movements'] else str(row['closing_value'])}
                 for row in sorted(values.values(), key=lambda item: item['name'].casefold())]}


@router.get('/api/companies/{company_id}/reports/stock/{item_id}/movements')
def item_stock_movements(company_id: str, item_id: str, from_date: DateType, to_date: DateType,
        user: User = Depends(current_user), session: Session = Depends(db),
        before_date: DateType | None = None, before_id: str | None = Query(default=None, max_length=80),
        limit: int = Query(default=50, ge=1, le=100)):
    company_for(company_id, user, session)
    if from_date > to_date:
        raise HTTPException(422, 'Start date must be before end date')
    if (before_date is None) != (before_id is None):
        raise HTTPException(422, 'Provide both fields for the next page of stock movements')
    item = session.scalar(select(Record.id).where(Record.company_id == company_id,
        Record.id == item_id, Record.kind == 'item'))
    if item is None:
        raise HTTPException(404, 'Item not found')
    query = select(StockMovement, Record.kind, Record.number).join(
        Record, Record.id == StockMovement.source_record_id).where(
            StockMovement.company_id == company_id, StockMovement.item_id == item_id,
            Record.company_id == company_id, StockMovement.date.between(from_date, to_date))
    if before_date is not None:
        query = query.where(or_(StockMovement.date < before_date,
            (StockMovement.date == before_date) & (StockMovement.id < before_id)))
    results = session.execute(query.order_by(StockMovement.date.desc(), StockMovement.id.desc()).limit(limit + 1)).all()
    rows = [{'id': movement.id, 'date': movement.date, 'quantity': str(movement.quantity),
             'cost_value': str(movement.cost_value) if movement.cost_value is not None else None,
             'record_id': movement.source_record_id, 'kind': kind, 'number': number}
            for movement, kind, number in results[:limit]]
    next_page = {'date': rows[-1]['date'], 'id': rows[-1]['id']} if len(results) > limit else None
    return {'rows': rows, 'next': next_page}


@router.get('/api/companies/{company_id}/reports/stock.{fmt}')
def export_stock(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    from routers.reports import export_table
    company = company_for(company_id, user, session)
    data = stock_report(company_id, from_date, to_date, user, session)
    rows = [[row[key] for key in ('name', 'unit', 'opening_quantity', 'introduced_quantity', 'adjustment_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity')]
            + [row['closing_value'] if row['closing_value'] is not None else 'Needs migration'] for row in data['rows']]
    return export_table(company.name, f"Tracked stock {from_date} to {to_date}",
        ['Item', 'Unit', 'Opening', 'Stock introduced', 'Adjustments net', 'Purchased net', 'Sold net', 'Closing', 'Closing cost value'], rows, fmt, 'tracked-stock')
