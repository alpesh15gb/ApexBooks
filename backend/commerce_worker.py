"""Durable Bagisto worker. Run as a separate process, never FastAPI BackgroundTasks."""
import argparse
import time
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, update, insert, or_, and_
from sqlalchemy.orm import Session
import main as m
from commerce import now, later, remote


def claim(direction, connection_id=None):
    service = m.commerce; t = service.t[direction]; ct = service.t['connections']
    with Session(m.engine) as session:
        query = select(t).join(ct, t.c.connection_id == ct.c.id).where(
            or_(and_(t.c.status.in_(['pending', 'retry']), t.c.available_at <= now()),
                and_(t.c.status == 'processing', t.c.lease_until < now())),
            ct.c.status != 'draft' if direction == 'inbox' else ct.c.status == 'active')
        if connection_id: query = query.where(t.c.connection_id == connection_id)
        row = session.execute(query.order_by(t.c.created_at, t.c.id).limit(1).with_for_update(of=t, skip_locked=True)).mappings().first()
        if not row: return None
        lease = later(120)
        result = session.execute(update(t).where(t.c.id == row['id'], t.c.status == row['status'],
            t.c.lease_until == row['lease_until'] if row['lease_until'] else t.c.lease_until.is_(None)).values(
                status='processing', lease_until=lease, attempts=t.c.attempts + 1))
        if result.rowcount != 1: session.rollback(); return None
        session.commit(); return dict(row) | {'lease_until': lease, 'attempts': row['attempts'] + 1}


def finish(direction, job, *, result=None, error=None):
    t = m.commerce.t[direction]
    retry = error is not None and (not isinstance(error, HTTPException) or error.status_code in (429, 503)) and job['attempts'] < 12
    values = {'status': 'done' if error is None else 'retry' if retry else 'review', 'lease_until': None,
        'error': '' if error is None else str(error.detail if isinstance(error, HTTPException) else 'Worker failed; review server logs')[:500],
        'result': result or {}, 'available_at': later(min(1800, 2 ** min(job['attempts'], 10))) if retry else now()}
    with Session(m.engine) as session:
        session.execute(update(t).where(t.c.id == job['id'], t.c.status == 'processing', t.c.lease_until == job['lease_until']).values(**values)); session.commit()


def process_one(direction, connection_id=None):
    job = claim(direction, connection_id)
    if not job: return False
    service = m.commerce; t = service.t[direction]
    try:
        with Session(m.engine) as session:
            c = service.one(session, service.t['connections'], service.t['connections'].c.id == job['connection_id'],
                service.t['connections'].c.company_id == job['company_id'], service.t['connections'].c.tenant_id == job['tenant_id'])
            company = session.get(m.Company, job['company_id'])
            if not c or not company or company.owner_id != job['tenant_id']: raise HTTPException(409, 'Integration ownership changed; reconnect before continuing')
            if direction == 'inbox':
                m.lock_company(company.id, session.get(m.User, c['tenant_id']), session)
                current = session.execute(select(t).where(t.c.id == job['id']).with_for_update(of=t)).mappings().first()
                if current['status'] != 'processing' or current['lease_until'] != job['lease_until']: return True
                result = service.process(session, c, job)
                session.execute(update(t).where(t.c.id == job['id'], t.c.lease_until == job['lease_until']).values(status='done', lease_until=None, error='', result=result))
                session.commit()
            else:
                packet = job['payload'].get('_delivery')
                if packet is None:
                    payload = dict(job['payload'])
                    if job['operation'] in ('stock.project', 'catalogue.publish'):
                        m.lock_company(company.id, session.get(m.User, c['tenant_id']), session)
                        c = service.one(session, service.t['connections'], service.t['connections'].c.id == c['id'])
                        payload = {'stock' if job['operation'] == 'stock.project' else 'products': service.stocks(session, c), 'projection_version': c['version']}
                    packet = {'command_id': job['command_id'], 'operation': job['operation'], 'channel': c['channel'], 'payload': payload}
                    updated = session.execute(update(t).where(t.c.id == job['id'], t.c.status == 'processing', t.c.lease_until == job['lease_until']).values(payload={'_delivery': packet}))
                    if updated.rowcount != 1: session.rollback(); return True
                    session.commit()  # Freeze exact delivery before any network side effect.
                else: session.rollback()
                result = remote(service, c, 'POST', '/apex-bridge/v1/commands', packet)
                if result.get('status') == 'pending': raise HTTPException(503, 'Store command is pending; retry will recover its result')
                if result.get('status') != 'done': raise HTTPException(409, result.get('error', 'Store rejected this action'))
                if job['operation'] == 'reconcile.snapshot':
                    with Session(m.engine) as check:
                        from decimal import Decimal
                        expected = {r['external_id']: r for r in service.stocks(check, c) if r['track_stock']}
                        observed = {str(r['external_id']): r for r in result.get('stock', [])}
                        differences = [{'product_id': key, 'expected': r['available_quantity'], 'actual': observed.get(key, {}).get('available_quantity')}
                            for key, r in expected.items() if key not in observed or Decimal(str(observed[key]['available_quantity'])) != Decimal(r['available_quantity'])]
                        totals = {'invoice_total': Decimal(0), 'credit_total': Decimal(0), 'captured_total': Decimal(0), 'refunded_total': Decimal(0),
                            'settled_gross_total': Decimal(0), 'settled_net_total': Decimal(0), 'fee_total': Decimal(0)}
                        links = service.t['links']
                        for link in check.execute(select(links).where(links.c.connection_id == c['id'])).mappings():
                            key = {'invoice':'invoice_total', 'credit':'credit_total', 'capture':'captured_total', 'refund':'refunded_total'}.get(link['entity_type'])
                            if key: totals[key] += check.get(m.Record, link['record_id']).amount
                            if link['entity_type'] == 'settlement':
                                for dest, source in [('settled_gross_total','gross'), ('settled_net_total','net'), ('fee_total','fee')]: totals[dest] += Decimal(str(link['snapshot'][source]))
                        financial_differences = [{'total': key, 'expected': str(value), 'actual': result.get('summary', {}).get(key)} for key, value in totals.items()
                            if key not in result.get('summary', {}) or Decimal(str(result['summary'][key])) != value]
                        check.execute(insert(service.t['reconciliations']).values(id=str(uuid4()), **service.fields(c), created_at=now(),
                            status='balanced' if not differences and not financial_differences else 'review', report={'stock_differences': differences,
                                'financial_differences': financial_differences, 'books': {key:str(value) for key,value in totals.items()}, 'store': result.get('summary', {})})); check.commit()
                finish(direction, job, result=result)
    except Exception as error:
        finish(direction, job, error=error)
    return True


def run_once(limit=100, connection_id=None):
    count = 0
    for _ in range(limit):
        incoming = process_one('inbox', connection_id)
        outgoing = process_one('outbox', connection_id)
        count += int(incoming) + int(outgoing)
        if not incoming and not outgoing: break
    return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    while True:
        run_once(max(1, min(args.limit, 500)))
        if args.once: break
        time.sleep(2)
