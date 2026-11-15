"""One optional till shared by all POS clients within a company."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from business_calendar import business_today
from pos_validation import payment_amount, requote_required


SESSION = 'pos_register_session'
MOVEMENT = 'pos_register_movement'
SESSION_ID = 'pos_register_session_id'
EXPECTED_SESSION = 'expected_register_session'
UNSPECIFIED = object()
ZERO = Decimal('0.00')


class RegisterInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OpenRegister(RegisterInput):
    opening_float: Decimal = Field(ge=0, max_digits=15, decimal_places=2)


class CashMovement(RegisterInput):
    direction: Literal['in', 'out']
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    reason: str = Field(min_length=1, max_length=200)


class CloseRegister(RegisterInput):
    counted_cash: Decimal = Field(ge=0, max_digits=15, decimal_places=2)
    snapshot: str = Field(pattern=r'^[0-9a-f]{64}$')
    reason: str = Field(default='', max_length=200)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def active_session(m, company_id, session):
    return session.scalar(select(m.Record).where(
        m.Record.company_id == company_id, m.Record.kind == SESSION,
        m.Record.data['closed_at'].as_string().is_(None),
    ).limit(1))


def tag_posting(m, company_id, data, session, historical_record=None):
    """Called under the company write lock, after replay lookup."""
    data.pop(SESSION_ID, None)
    expected = data.pop(EXPECTED_SESSION, UNSPECIFIED)
    if expected is not UNSPECIFIED and expected is not None and not isinstance(expected, str):
        raise HTTPException(422, 'Invalid expected POS register session')
    if historical_record is not None:
        register_id = historical_record.data.get(SESSION_ID)
    else:
        register = active_session(m, company_id, session)
        register_id = register.id if register else None
    if expected is not UNSPECIFIED and expected != register_id:
        raise requote_required('POS register changed. Review the active register and checkout total.')
    if register_id:
        data[SESSION_ID] = register_id


def require_unclosed(m, record, session):
    register_id = record.data.get(SESSION_ID)
    if register_id:
        register = session.get(m.Record, register_id)
        if not register or register.company_id != record.company_id or register.kind != SESSION:
            raise HTTPException(409, 'The posting has an invalid POS register link')
        if register.data.get('closed_at'):
            raise HTTPException(409, 'This POS register is closed. Use a linked correction or return.')


def rollup(register, entries):
    summary = {
        'cash_sales': ZERO, 'bank_sales': ZERO, 'cash_refunds': ZERO,
        'bank_refunds': ZERO, 'cash_in': ZERO, 'cash_out': ZERO,
    }
    counts = {'sales_count': 0, 'refund_count': 0, 'movement_count': 0}
    evidence = []
    for row in entries:
        data = row['data']
        amount = Decimal(str(row['amount'])).quantize(ZERO)
        if row['kind'] == MOVEMENT:
            direction = data['direction']
            summary[f'cash_{direction}'] += amount
            counts['movement_count'] += 1
            evidence.append([row['id'], direction, str(amount)])
            continue
        label = 'sales' if row['kind'] == 'pos' else 'refunds'
        method = data.get('payment_account', 'cash')
        if method == 'cash':
            cash, bank = amount, ZERO
        elif method == 'bank':
            cash, bank = ZERO, amount
        elif method == 'split' and row['kind'] == 'pos':
            cash, bank = Decimal(data['cash_amount']).quantize(ZERO), Decimal(data['bank_amount']).quantize(ZERO)
            if min(cash, bank) <= ZERO or cash + bank != amount:
                raise ValueError('Invalid register split tender')
        else:
            raise ValueError('Invalid register tender')
        summary[f'cash_{label}'] += cash
        summary[f'bank_{label}'] += bank
        counts['sales_count' if label == 'sales' else 'refund_count'] += 1
        evidence.append([row['id'], label, str(cash), str(bank)])
    summary['expected_cash'] = (
        Decimal(register['data']['opening_float']) + summary['cash_sales'] - summary['cash_refunds']
        + summary['cash_in'] - summary['cash_out']
    )
    return {**{key: str(value) for key, value in summary.items()}, **counts}, digest(sorted(evidence))


def live_entries(m, register, session):
    return [m.obj(row) for row, posting in session.execute(
        select(m.Record, m.RecordPosting.id).outerjoin(
            m.RecordPosting, (m.RecordPosting.record_id == m.Record.id)
            & (m.RecordPosting.company_id == register.company_id),
        ).where(
            m.Record.company_id == register.company_id,
            m.Record.kind.in_((MOVEMENT, 'pos', 'customer_refund')),
            m.Record.data[SESSION_ID].as_string() == register.id,
        )
    ) if row.kind == MOVEMENT or (posting and not row.data.get('cancelled'))]


def register_view(m, register, session, *, include_activity=True):
    result = m.obj(register)
    if not include_activity:
        return result
    entries = live_entries(m, register, session)
    result['movements'] = sorted(
        (row for row in entries if row['kind'] == MOVEMENT),
        key=lambda row: (row['data']['created_at'], row['id']), reverse=True,
    )[:100]
    if not register.data.get('closed_at'):
        result['totals'], result['snapshot'] = rollup(result, entries)
    return result


def validate_backup(groups, indexes, posted):
    sessions = {}
    operations = {}
    periods = []

    def actor(value):
        return isinstance(value, str) and 0 < len(value) <= 320

    def amount(value, *, signed=False):
        if not isinstance(value, str):
            raise ValueError('Invalid register cash amount')
        try:
            amount = Decimal(value)
            if not amount.is_finite() or amount < ZERO and not signed or amount != amount.quantize(ZERO):
                raise ValueError('Invalid register cash amount')
            return amount
        except ArithmeticError as error:
            raise ValueError('Invalid register cash amount') from error

    def timestamp(value):
        if not isinstance(value, str):
            raise ValueError('Invalid register event time')
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError('Invalid register event time')
        return result

    for row in groups['records']:
        if row['kind'] != SESSION:
            continue
        sid = row['id']
        data = row['data']
        opened = timestamp(data.get('created_at'))
        if sid in posted or Decimal(str(row['amount'])) != ZERO or not actor(data.get('opened_by')):
            raise ValueError('Invalid POS register session')
        if amount(data.get('opening_float')) > Decimal('9999999999999.99'):
            raise ValueError('Invalid register opening float')
        closed = None
        if 'closed_at' in data:
            closed = timestamp(data['closed_at'])
            if closed < opened or not actor(data.get('closed_by')):
                raise ValueError('Invalid POS register close')
            if amount(data.get('counted_cash')) > Decimal('9999999999999.99'):
                raise ValueError('Invalid register count')
        elif any(key in data for key in ('closed_by', 'closed_totals', 'counted_cash', 'variance', 'close_reason')):
            raise ValueError('Incomplete POS register close')
        sessions[sid] = row
        operations[sid] = []
        periods.append((opened, closed))

    periods.sort(key=lambda period: period[0])
    for previous, following in zip(periods, periods[1:]):
        if previous[1] is None or previous[1] > following[0]:
            raise ValueError('Overlapping POS register sessions')

    for row in groups['records']:
        data = row['data']
        register_id = data.get(SESSION_ID)
        if SESSION_ID not in data and row['kind'] != MOVEMENT:
            continue
        if not isinstance(register_id, str) or register_id not in sessions:
            raise ValueError('Invalid POS register link')
        if row['kind'] == MOVEMENT:
            entry_time = timestamp(data.get('created_at'))
            register_data = sessions[register_id]['data']
            if (row['id'] in posted or data.get('direction') not in ('in', 'out')
                    or Decimal(str(row['amount'])) <= ZERO or not actor(data.get('actor'))
                    or not isinstance(data.get('reason'), str) or not 0 < len(data['reason'].strip()) <= 200
                    or entry_time < timestamp(register_data['created_at'])
                    or 'closed_at' in register_data and entry_time > timestamp(register_data['closed_at'])):
                raise ValueError('Invalid POS register cash movement')
            operations[register_id].append(row)
        elif row['kind'] in ('pos', 'customer_refund'):
            if row['kind'] == 'customer_refund':
                records = indexes['records']
                credit_id = data.get('credit_note_id')
                note = records.get(credit_id, {}) if isinstance(credit_id, str) else {}
                source_id = note.get('data', {}).get('applied_to')
                source = records.get(source_id, {}) if isinstance(source_id, str) else {}
                if note.get('kind') != 'credit_note' or source.get('kind') != 'pos':
                    raise ValueError('POS register refund has no POS source')
            if row['id'] in posted and not data.get('cancelled'):
                # Backup record amounts may be represented as JSON numbers.
                operations[register_id].append({**row, 'amount': str(row['amount'])})
        else:
            raise ValueError('Invalid register posting kind')

    for sid, register in sessions.items():
        data = register['data']
        totals, _ = rollup(register, operations[sid])
        if 'closed_at' in data:
            difference = amount(data['counted_cash']) - Decimal(totals['expected_cash'])
            reason = data.get('close_reason')
            if (data.get('closed_totals') != totals or amount(data.get('variance'), signed=True) != difference
                    or not isinstance(reason, str) or len(reason) > 200 or difference and not reason.strip()):
                raise ValueError('Invalid POS register close totals')


def install(app, m):
    base = '/api/companies/{company_id}/pos-register'

    @app.get(base)
    def get_register(company_id: str, user=Depends(m.current_user), session: Session = Depends(m.db)):
        m.company_for(company_id, user, session)
        register = active_session(m, company_id, session)
        recent = session.scalars(select(m.Record).where(
            m.Record.company_id == company_id, m.Record.kind == SESSION,
            m.Record.data['closed_at'].as_string().is_not(None),
        ).order_by(m.Record.data['closed_at'].as_string().desc(), m.Record.id.desc()).limit(10))
        return {
            'active': register_view(m, register, session) if register else None,
            'closed': [register_view(m, row, session, include_activity=False) for row in recent],
        }

    @app.get(base + '/{register_id}')
    def get_session(company_id: str, register_id: str, user=Depends(m.current_user), session: Session = Depends(m.db)):
        m.company_for(company_id, user, session)
        return register_view(m, get_one(company_id, register_id, session), session)

    def get_one(company_id, register_id, session):
        register = session.get(m.Record, register_id)
        if not register or register.company_id != company_id or register.kind != SESSION:
            raise HTTPException(404, 'POS register session not found')
        return register

    def ensure_open(company_id, register_id, session):
        register = get_one(company_id, register_id, session)
        if register.data.get('closed_at'):
            raise HTTPException(409, 'This POS register is already closed')
        return register

    def retry(company_id, operation, body, request, user, session):
        m.lock_company(company_id, user, session)
        key = request.headers.get('Idempotency-Key', '').strip()
        if not key or len(key) > 80:
            raise HTTPException(422, 'A retry key is required')
        request_hash = digest({'operation': operation, 'body': body.model_dump(mode='json')})
        old = session.scalar(select(m.IdempotencyKey).where(
            m.IdempotencyKey.company_id == company_id, m.IdempotencyKey.key == key,
        ))
        if old and old.request_hash != request_hash:
            raise HTTPException(409, 'Idempotency key was used for a different request')
        return key, request_hash, session.get(m.Record, old.record_id) if old else None

    def save(key, request_hash, row, user, action, session):
        session.flush()
        session.add(m.IdempotencyKey(
            company_id=row.company_id, key=key, request_hash=request_hash, record_id=row.id,
        ))
        m.audit(session, row.company_id, user, action, 'pos_register', row.id)
        session.commit()

    @app.post(base + '/open', status_code=201)
    def open_session(company_id: str, body: OpenRegister, request: Request, user=Depends(m.current_user), session: Session = Depends(m.db)):
        key, request_hash, old = retry(company_id, 'pos_register.open', body, request, user, session)
        if old:
            return register_view(m, old, session)
        if active_session(m, company_id, session):
            raise HTTPException(409, 'A POS register session is already open')
        opening = payment_amount(body.opening_float, 'Enter a valid opening float')
        opened_at = now()
        row = m.Record(company_id=company_id, kind=SESSION, name='POS register',
                       date=business_today(), amount=ZERO,
                       data={'created_at': opened_at, 'opened_by': user.email, 'opening_float': str(opening)})
        session.add(row)
        save(key, request_hash, row, user, 'pos_register.opened', session)
        return register_view(m, row, session)

    @app.post(base + '/{register_id}/movements', status_code=201)
    def move_cash(company_id: str, register_id: str, body: CashMovement, request: Request, user=Depends(m.current_user), session: Session = Depends(m.db)):
        key, request_hash, old = retry(company_id, 'pos_register.movement:' + register_id, body, request, user, session)
        if old:
            return m.obj(old)
        ensure_open(company_id, register_id, session)
        reason = body.reason.strip()
        if not reason:
            raise HTTPException(422, 'Enter a reason for the drawer movement')
        amount = payment_amount(body.amount, 'Enter a valid cash amount')
        row = m.Record(company_id=company_id, kind=MOVEMENT, name='Drawer movement',
                       date=business_today(), amount=amount, data={
                           SESSION_ID: register_id, 'created_at': now(), 'actor': user.email,
                           'direction': body.direction, 'reason': reason,
                       })
        session.add(row)
        save(key, request_hash, row, user, 'pos_register.cash_' + body.direction, session)
        return m.obj(row)

    @app.post(base + '/{register_id}/close')
    def close_session(company_id: str, register_id: str, body: CloseRegister, request: Request, user=Depends(m.current_user), session: Session = Depends(m.db)):
        key, request_hash, old = retry(company_id, 'pos_register.close:' + register_id, body, request, user, session)
        if old:
            return register_view(m, old, session)
        row = ensure_open(company_id, register_id, session)
        totals, snapshot = rollup(m.obj(row), live_entries(m, row, session))
        if snapshot != body.snapshot:
            raise HTTPException(409, 'Register activity changed. Refresh and review the current drawer total.')
        counted = payment_amount(body.counted_cash, 'Enter a valid closing count')
        variance = counted - Decimal(totals['expected_cash'])
        reason = body.reason.strip()
        if variance and not reason:
            raise HTTPException(422, 'Enter a reason for the cash difference')
        row.data = {
            **row.data, 'closed_at': now(), 'closed_by': user.email, 'closed_totals': totals,
            'counted_cash': str(counted), 'variance': str(variance), 'close_reason': reason,
        }
        save(key, request_hash, row, user, 'pos_register.closed', session)
        return register_view(m, row, session)
