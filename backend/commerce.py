"""Company-bound Bagisto integration, durable messages and shared stock reservations."""
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, insert, update, func, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from commerce_schema import schema_current

OWN_RESERVATION = ContextVar('commerce_own_reservation', default=None)
EVENTS = {'product.upsert', 'customer.upsert', 'order.upsert', 'order.cancelled',
          'invoice.created', 'payment.captured', 'refund.created', 'payment.refunded',
          'shipment.updated', 'settlement.created', 'return.received'}
OPERATIONS = {'catalogue.publish', 'catalogue.scan', 'history.scan', 'order.invoice', 'order.ship', 'order.cancel',
              'order.refund', 'stock.project', 'reconcile.snapshot', 'payment.capture', 'payment.refund', 'settlement.record', 'return.receive'}

_last_stamp = [datetime.min.replace(tzinfo=timezone.utc)]
_stamp_lock = __import__('threading').Lock()
def now():
    """Strictly increasing UTC stamp: coarse clocks (Windows ~15 ms) must not tie queued events into random UUID order."""
    with _stamp_lock:
        current = datetime.now(timezone.utc)
        if current <= _last_stamp[0]: current = _last_stamp[0] + timedelta(microseconds=1)
        _last_stamp[0] = current
        return current.isoformat(timespec='microseconds')
def later(seconds): return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
def encode(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def digest(value): return hashlib.sha256(encode(value)).hexdigest()
def decimal(value, *, positive=False):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or positive and result <= 0 or result > Decimal('999999999999.999'): raise ValueError()
        return result
    except Exception: raise HTTPException(422, 'Enter a finite nonnegative amount or quantity')

def cipher():
    key = os.getenv('COMMERCE_ENCRYPTION_KEY', '')
    if not key: raise HTTPException(503, 'Commerce secret encryption is not configured on the server')
    try: return Fernet(key.encode())
    except ValueError: raise HTTPException(503, 'Commerce encryption key configuration is invalid')

def validate_url(value):
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.strip('/'):
        raise HTTPException(422, 'Use the store origin without credentials, path, query or fragment')
    host = (parsed.hostname or '').lower()
    local = os.getenv('COMMERCE_ALLOW_LOCALHOST') == '1' and host in {'localhost', '127.0.0.1', 'host.docker.internal', 'bagisto'}
    if parsed.scheme != 'https' and not (local and parsed.scheme == 'http'):
        raise HTTPException(422, 'Use HTTPS for the Bagisto store')
    allowed = {x.strip().lower() for x in os.getenv('COMMERCE_ALLOWED_HOSTS', '').split(',') if x.strip()}
    if not local and host not in allowed:
        raise HTTPException(422, 'The server administrator must allow this store hostname in COMMERCE_ALLOWED_HOSTS')
    if not local:
        try:
            addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses): raise ValueError()
        except (OSError, ValueError): raise HTTPException(422, 'Store hostname must resolve to public addresses')
    return value.rstrip('/')

def signature(secret, timestamp, method, path, body):
    message = f'{timestamp}\n{method.upper()}\n{path}\n{hashlib.sha256(body).hexdigest()}'.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

class Strict(BaseModel): model_config = ConfigDict(extra='forbid')
class ConnectionInput(Strict):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(max_length=500)
    channel: str = Field(min_length=1, max_length=100)
    currency: str = 'INR'
    gateway_bank_id: str = 'default'
class ConnectionState(Strict):
    status: str = Field(pattern='^(active|paused)$')
class LinkInput(Strict):
    entity_type: str = Field(pattern='^(product|customer)$')
    external_id: str = Field(min_length=1, max_length=160)
    record_id: str
    sku: str | None = Field(default=None, max_length=100)
class EventInput(Strict):
    event_id: str = Field(min_length=1, max_length=160)
    event_type: str
    entity_id: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1, le=9_007_199_254_740_991)
    channel: str = Field(min_length=1, max_length=100)
    payload: dict
class ReservationLine(Strict):
    external_product_id: str = Field(min_length=1, max_length=160)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
class ReserveInput(Strict):
    reference: str = Field(min_length=1, max_length=160)
    channel: str
    lines: list[ReservationLine] = Field(min_length=1, max_length=100)
    expires_seconds: int = Field(default=900, ge=60, le=3600)
class ReservationAction(Strict):
    action: str = Field(pattern='^(confirm|release)$')
    order_id: str = Field(default='', max_length=160)
class CommandInput(Strict):
    command_id: str = Field(min_length=1, max_length=100)
    operation: str
    payload: dict = Field(default_factory=dict)

class Commerce:
    def __init__(self, m):
        self.m, self.t = m, schema_current(m.Base.metadata)
    def one(self, session, table, *conditions):
        return session.execute(select(table).where(*conditions)).mappings().first()
    def scoped(self, session, company, connection_id):
        row = self.one(session, self.t['connections'], self.t['connections'].c.id == connection_id,
            self.t['connections'].c.company_id == company.id, self.t['connections'].c.tenant_id == company.owner_id)
        if not row: raise HTTPException(404, 'Store connection not found in this company')
        return row
    def fields(self, c): return {key: c[key] for key in ('tenant_id', 'company_id')} | {'connection_id': c['id']}
    def public_connection(self, c):
        return {k: c[k] for k in ('id', 'tenant_id', 'company_id', 'name', 'base_url', 'channel', 'currency', 'status', 'config', 'version', 'created_at', 'updated_at')}
    def secret(self, c):
        try: return cipher().decrypt(c['secret'].encode()).decode()
        except InvalidToken: raise HTTPException(503, 'Connection credentials cannot be decrypted; restore the commerce encryption key')
    def service(self, session, connection_id, request, body):
        c = self.one(session, self.t['connections'], self.t['connections'].c.id == connection_id)
        if not c: raise HTTPException(401, 'Invalid integration signature')
        timestamp = request.headers.get('X-Apex-Timestamp', '')
        try:
            if abs(time.time() - int(timestamp)) > 300: raise ValueError()
        except ValueError: raise HTTPException(401, 'Integration timestamp is expired')
        if not hmac.compare_digest(signature(self.secret(c), timestamp, request.method, request.url.path, body), request.headers.get('X-Apex-Signature', '')):
            raise HTTPException(401, 'Invalid integration signature')
        company = session.get(self.m.Company, c['company_id'])
        if not company or company.owner_id != c['tenant_id']: raise HTTPException(401, 'Connection ownership changed')
        return c
    def link(self, session, c, entity_type, external_id):
        t = self.t['links']
        return self.one(session, t, t.c.connection_id == c['id'], t.c.company_id == c['company_id'],
            t.c.tenant_id == c['tenant_id'], t.c.entity_type == entity_type, t.c.external_id == str(external_id))
    def add_link(self, session, c, kind, external_id, record_id=None, sku=None, version=1, snapshot=None):
        old = self.link(session, c, kind, external_id)
        values = dict(record_id=record_id, sku=sku, version=version, snapshot=snapshot or {})
        if old: session.execute(update(self.t['links']).where(self.t['links'].c.id == old['id']).values(**values))
        else: session.execute(insert(self.t['links']).values(id=str(uuid4()), **self.fields(c), entity_type=kind, external_id=str(external_id), **values))
    def active_holds(self, session, cid, exclude=None):
        t = self.t['reservations']
        return session.execute(select(t).where(t.c.company_id == cid, t.c.status.in_(['held', 'confirmed']),
            or_(t.c.status == 'confirmed', t.c.expires_at > now()), t.c.id != exclude if exclude else True)).mappings().all()
    def reserved(self, session, cid, item_id, exclude=None):
        return sum((decimal(line['quantity']) - decimal(line.get('consumed', '0')) for r in self.active_holds(session, cid, exclude)
            for line in r['lines'] if line['item_id'] == item_id), Decimal(0))
    def book_quantity(self, session, cid, item_id):
        return session.scalar(select(func.coalesce(func.sum(self.m.StockMovement.quantity), 0)).where(
            self.m.StockMovement.company_id == cid, self.m.StockMovement.item_id == item_id))
    def available(self, session, cid, item_id, exclude=None):
        return self.book_quantity(session, cid, item_id) - self.reserved(session, cid, item_id, exclude)
    def assert_available(self, cid, item_id, quantity, book_quantity, session):
        reserved = self.reserved(session, cid, item_id, OWN_RESERVATION.get())
        if reserved > 0 and quantity > max(Decimal(0), book_quantity - reserved):
            raise HTTPException(409, 'Stock is reserved for accepted online orders; reduce quantity or release the order reservation')
    def enqueue(self, session, c, command_id, operation, payload):
        if operation not in OPERATIONS: raise HTTPException(422, 'Unsupported commerce action')
        t = self.t['outbox']; hashed = digest({'operation': operation, 'payload': payload})
        old = self.one(session, t, t.c.connection_id == c['id'], t.c.command_id == command_id)
        if old:
            if old['request_hash'] != hashed: raise HTTPException(409, 'Command identity already has a different payload')
            return dict(old)
        stamp = now(); row = dict(id=str(uuid4()), **self.fields(c), command_id=command_id, operation=operation,
            payload=payload, request_hash=hashed, status='pending', attempts=0, available_at=stamp, lease_until=None,
            error='', result={}, created_at=stamp)
        session.execute(insert(t).values(**row)); return row
    def stock_changed(self, cid, session):
        t = self.t['connections']
        for c in session.execute(select(t).where(t.c.company_id == cid, t.c.status == 'active')).mappings():
            session.execute(update(t).where(t.c.id == c['id']).values(version=t.c.version + 1, updated_at=now()))
            self.enqueue(session, c, 'stock-' + str(uuid4()), 'stock.project', {})
    def stocks(self, session, c):
        t = self.t['links']; rows = []
        profile = session.get(self.m.CompanyTaxProfile, c['company_id'])
        regular = not profile or profile.mode == 'regular'
        for link in session.execute(select(t).where(t.c.connection_id == c['id'], t.c.entity_type == 'product')).mappings():
            item = session.get(self.m.Record, link['record_id'])
            if item and item.company_id == c['company_id']:
                rows.append({'external_id': link['external_id'], 'item_id': item.id, 'sku': link['sku'],
                    'name': item.name, 'track_stock': bool(item.data.get('track_stock')),
                    'book_quantity': str(self.book_quantity(session, c['company_id'], item.id)),
                    'reserved_quantity': str(self.reserved(session, c['company_id'], item.id)),
                    'available_quantity': str(max(Decimal(0), self.available(session, c['company_id'], item.id))),
                    'sale_rate': item.data.get('sale_rate', '0'),
                    'gst_rate': item.data.get('gst_rate', '0') if regular and item.data.get('tax_treatment', 'taxable') == 'taxable' else '0',
                    'tax_treatment': item.data.get('tax_treatment', 'taxable'),
                    'hsn': item.data.get('hsn', ''), 'unit': item.data.get('unit', '')})
        return rows
    def reserve(self, session, c, body):
        if c['status'] != 'active': raise HTTPException(409, 'Store connection is not active')
        if body.channel != c['channel']: raise HTTPException(422, 'Channel does not match this connection')
        self.m.lock_company(c['company_id'], session.get(self.m.User, c['tenant_id']), session)
        t = self.t['reservations']; hashed = digest(body.model_dump(mode='json'))
        old = self.one(session, t, t.c.connection_id == c['id'], t.c.reference == body.reference)
        if old:
            if old['request_hash'] != hashed: raise HTTPException(409, 'Reservation reference has different lines')
            if old['status'] not in ('held', 'confirmed') or old['status'] == 'held' and old['expires_at'] <= now():
                raise HTTPException(409, 'Reservation is no longer available; use a new checkout reference')
            return dict(old)
        lines, totals = [], {}
        for line in body.lines:
            link = self.link(session, c, 'product', line.external_product_id)
            if not link: raise HTTPException(422, 'Map each store product to an item before accepting checkout')
            item = session.get(self.m.Record, link['record_id'])
            if not item or item.company_id != c['company_id'] or item.kind != 'item': raise HTTPException(422, 'Invalid company item mapping')
            if not item.data.get('track_stock'): continue
            totals[item.id] = totals.get(item.id, Decimal(0)) + line.quantity
            lines.append({'item_id': item.id, 'external_product_id': line.external_product_id, 'quantity': str(line.quantity), 'consumed': '0'})
        for item_id, qty in totals.items():
            if qty > self.available(session, c['company_id'], item_id): raise HTTPException(409, 'Insufficient available stock for checkout')
        row = dict(id=str(uuid4()), **self.fields(c), reference=body.reference, status='held', expires_at=later(body.expires_seconds),
            lines=lines, request_hash=hashed, order_id=None, updated_at=now())
        session.execute(insert(t).values(**row)); self.stock_changed(c['company_id'], session); return row
    def reservation_action(self, session, c, reservation_id, body):
        self.m.lock_company(c['company_id'], session.get(self.m.User, c['tenant_id']), session)
        t = self.t['reservations']; old = self.one(session, t, t.c.id == reservation_id, t.c.connection_id == c['id'])
        if not old: raise HTTPException(404, 'Reservation not found')
        if body.action == 'confirm':
            if not body.order_id: raise HTTPException(422, 'Order identity is required')
            if old['status'] not in ('held', 'confirmed') or old['status'] == 'held' and old['expires_at'] <= now(): raise HTTPException(409, 'Reservation expired or released')
            if old['order_id'] and old['order_id'] != body.order_id: raise HTTPException(409, 'Reservation already belongs to a different order')
            values = {'status': 'confirmed', 'order_id': body.order_id}
        else:
            if old['status'] == 'consumed': raise HTTPException(409, 'Invoiced stock must be corrected through a linked return')
            values = {'status': 'released'}
        session.execute(update(t).where(t.c.id == old['id']).values(**values, updated_at=now()))
        self.stock_changed(c['company_id'], session)
        return dict(old) | values
    def ingest(self, session, c, body):
        if c['status'] == 'draft': raise HTTPException(409, 'Verify and activate this connection before receiving events')
        if body.channel != c['channel'] or body.event_type not in EVENTS: raise HTTPException(422, 'Unsupported event or channel')
        if len(encode(body.payload)) > 1_000_000: raise HTTPException(413, 'Event payload is too large')
        t = self.t['inbox']; hashed = digest(body.model_dump(mode='json'))
        old = self.one(session, t, t.c.connection_id == c['id'], t.c.event_id == body.event_id)
        if old:
            if old['request_hash'] != hashed: raise HTTPException(409, 'Event identity has a different payload')
            return dict(old)
        stamp = now(); row = dict(id=str(uuid4()), **self.fields(c), **body.model_dump(exclude={'channel'}),
            request_hash=hashed, status='pending', attempts=0, available_at=stamp, lease_until=None, error='', result={}, created_at=stamp)
        session.execute(insert(t).values(**row)); return row

    def post(self, session, c, kind, name, issued, amount, data, identity):
        from copy import deepcopy
        key = 'commerce-' + hashlib.sha256((c['id'] + ':' + identity).encode()).hexdigest()[:64]
        body = self.m.RecordInput(kind=kind, name=name, date=date.fromisoformat(issued), amount=str(amount), data=deepcopy(data))
        return self.m.save_record(c['company_id'], body, SimpleNamespace(headers={'Idempotency-Key': key}),
            session.get(self.m.User, c['tenant_id']), session, commit=False)

    def order(self, session, c, external_id):
        t = self.t['orders']; row = self.one(session, t, t.c.connection_id == c['id'], t.c.external_id == str(external_id))
        if not row: raise HTTPException(503, 'Waiting for the source order event')
        return row

    def mapped_party(self, session, c, external_id):
        link = self.link(session, c, 'customer', external_id)
        if not link: raise HTTPException(503, 'Waiting for the source customer mapping')
        row = session.get(self.m.Record, link['record_id'])
        if not row or row.company_id != c['company_id'] or row.kind != 'party': raise HTTPException(422, 'Customer mapping is invalid')
        return row

    def invoice_lines(self, session, c, payload):
        lines = payload.get('lines')
        if not isinstance(lines, list) or not 1 <= len(lines) <= 100: raise HTTPException(422, 'Invoice requires 1–100 source lines')
        result = []
        for line in lines:
            link = self.link(session, c, 'product', line.get('product_id', ''))
            if not link: raise HTTPException(422, 'Map every invoice product before posting')
            item = session.get(self.m.Record, link['record_id'])
            if not item or item.company_id != c['company_id'] or item.kind != 'item': raise HTTPException(422, 'Product mapping is invalid')
            if not isinstance(line.get('price_includes_tax', False), bool): raise HTTPException(422, 'Tax-inclusive option must be boolean')
            result.append({'item_id': item.id, 'description': item.name, 'quantity': str(decimal(line.get('quantity'), positive=True)),
                'rate': str(decimal(line.get('rate'))), 'gst_rate': str(decimal(line.get('gst_rate', '0'))),
                'discount_amount': str(decimal(line.get('discount_amount', '0'))),
                'price_includes_tax': bool(line.get('price_includes_tax', False)),
                'hsn': item.data.get('hsn', ''), 'unit': item.data.get('unit', ''),
                'tax_treatment': line.get('tax_treatment', item.data.get('tax_treatment', 'taxable'))})
        if decimal(payload.get('shipping_amount', '0')):
            shipping = payload.get('shipping_line')
            if not isinstance(shipping, dict) or 'gst_rate' not in shipping or not shipping.get('hsn'):
                raise HTTPException(422, 'Map a reviewed shipping tax rate and HSN before posting delivery charges')
            result.append({'description': 'Delivery charges', 'quantity': '1', 'rate': str(decimal(payload['shipping_amount'])),
                'gst_rate': str(decimal(shipping['gst_rate'])), 'hsn': str(shipping['hsn']), 'unit': 'OTH',
                'tax_treatment': shipping.get('tax_treatment', 'taxable'), 'price_includes_tax': bool(shipping.get('price_includes_tax', False))})
        return result

    def apply_order_advances(self, session, c, order_id):
        m = self.m; t = self.t['links']
        links = list(session.execute(select(t).where(t.c.connection_id == c['id'], t.c.entity_type.in_(['capture', 'invoice']))).mappings())
        captures = [r for r in links if r['entity_type'] == 'capture' and r['snapshot'].get('order_id') == order_id]
        invoices = [r for r in links if r['entity_type'] == 'invoice' and r['snapshot'].get('order_id') == order_id]
        for capture in captures:
            source = session.get(m.Record, capture['record_id'])
            if not source or not source.data.get('is_advance'): continue
            for link in invoices:
                target = session.get(m.Record, link['record_id'])
                used = sum((r.amount for r in session.scalars(select(m.Record).where(m.Record.company_id == c['company_id'], m.Record.kind.in_(['advance_application', 'advance_refund']))) if r.data.get('advance_id') == source.id), Decimal(0))
                amount = min(source.amount - used, target.amount - m.applied_total(c['company_id'], target.id, session))
                if amount <= 0: continue
                key = 'commerce-apply-' + hashlib.sha256((source.id + target.id + str(used)).encode()).hexdigest()[:60]
                body = m.RecordInput(kind='advance_application', name=source.name, date=max(source.date, target.date), amount=str(amount), data={'applied_to': target.id})
                m.apply_advance_in_transaction(c['company_id'], source.id, body, SimpleNamespace(headers={'Idempotency-Key': key}), session.get(m.User, c['tenant_id']), session, commit=False)

    def process(self, session, c, event):
        m = self.m; p = event['payload']; kind = event['event_type']; external = event['entity_id']
        if p.get('_review'): raise HTTPException(422, str(p['_review'])[:300])
        if p.get('currency', c['currency']) != c['currency']: raise HTTPException(422, 'Order currency does not match the company integration')
        m.lock_company(c['company_id'], session.get(m.User, c['tenant_id']), session)
        if kind == 'product.upsert':
            link = self.link(session, c, 'product', external)
            if not link: raise HTTPException(422, 'Product needs reviewed item/SKU mapping')
            if event['version'] <= link['version']: return {'ignored': 'stale_product_version'}
            # Website metadata is mirrored separately; accounting prices/tax are not overwritten.
            self.add_link(session, c, 'product', external, link['record_id'], link['sku'], event['version'], p)
            return {'record_id': link['record_id'], 'metadata_updated': True}
        if kind == 'customer.upsert':
            link = self.link(session, c, 'customer', external)
            if link and event['version'] <= link['version']: return {'ignored': 'stale_customer_version'}
            if link:
                self.add_link(session, c, 'customer', external, link['record_id'], None, event['version'], p)
                return {'record_id': link['record_id'], 'contact_review': True}
            name = str(p.get('name', '')).strip()
            if not name or len(name) > 160: raise HTTPException(422, 'Customer name is required')
            existing = session.scalar(select(m.Record).where(m.Record.company_id == c['company_id'], m.Record.kind == 'party', func.lower(m.Record.name) == name.lower()))
            if existing:
                # Bagisto assigns each anonymous checkout a new guest order ID.
                # Reuse only an exact, unchanged contact already imported from
                # this connection; names or an email alone never merge parties.
                normalize = lambda value: ' '.join(str(value or '').split()).casefold()
                keys = ('name', 'email', 'phone', 'address', 'gstin')
                contact = {key: normalize(p.get(key)) for key in keys}
                current = {key: normalize(existing.name if key == 'name' else existing.data.get(key)) for key in keys}
                lt = self.t['links']
                if external.startswith('guest:') and all(contact[key] for key in ('email', 'phone', 'address')) and current == contact:
                    candidates = session.execute(select(lt).where(lt.c.connection_id == c['id'], lt.c.entity_type == 'customer',
                        lt.c.record_id == existing.id, lt.c.external_id.like('guest:%')).order_by(lt.c.version.desc()).limit(100)).mappings()
                    if any({key: normalize(row['snapshot'].get(key)) for key in keys} == contact for row in candidates):
                        self.add_link(session, c, 'customer', external, existing.id, None, event['version'], p)
                        return {'record_id': existing.id, 'repeat_guest': True}
                raise HTTPException(422, 'An existing party has this name; explicitly map the customer before importing')
            record = self.post(session, c, 'party', name, p.get('date', date.today().isoformat()), 0,
                {key: p.get(key, '') for key in ('gstin', 'address', 'phone', 'email')} | {'party_type': 'customer'}, 'customer:' + external)
            self.add_link(session, c, 'customer', external, record['id'], None, event['version'], p)
            return {'record_id': record['id']}
        if kind in ('order.upsert', 'order.cancelled', 'shipment.updated'):
            t = self.t['orders']; old = self.one(session, t, t.c.connection_id == c['id'], t.c.external_id == external)
            if old and event['version'] <= old['version']: return {'ignored': 'stale_order_version'}
            party = self.mapped_party(session, c, p.get('customer_id', old['snapshot'].get('customer_id') if old else ''))
            values = dict(number=str(p.get('number', external))[:160], version=event['version'],
                status='cancelled' if kind == 'order.cancelled' else str(p.get('status', 'pending'))[:40], party_id=party.id,
                amount=decimal(p.get('amount', old['amount'] if old else 0)), snapshot={**(old['snapshot'] if old else {}), **p}, updated_at=now())
            if old: session.execute(update(t).where(t.c.id == old['id']).values(**values))
            else: session.execute(insert(t).values(id=str(uuid4()), **self.fields(c), external_id=external, **values))
            hold_id = p.get('reservation_id') or (old['snapshot'].get('reservation_id') if old else None)
            if hold_id:
                rt = self.t['reservations']; hold = self.one(session, rt, rt.c.id == hold_id, rt.c.connection_id == c['id'])
                if not hold: raise HTTPException(422, 'Order reservation does not belong to this store')
                if kind == 'order.cancelled':
                    if hold['status'] not in ('consumed', 'released'): self.reservation_action(session, c, hold_id, ReservationAction(action='release'))
                elif hold['status'] == 'held': self.reservation_action(session, c, hold_id, ReservationAction(action='confirm', order_id=external))
            return {'order_id': old['id'] if old else external}
        identity = {'invoice.created': 'invoice', 'payment.captured': 'capture', 'refund.created': 'credit',
            'payment.refunded': 'refund', 'settlement.created': 'settlement', 'return.received': 'return'}.get(kind)
        previous = self.link(session, c, identity, external) if identity else None
        if previous:
            if previous['snapshot'].get('_hash') != digest(p): raise HTTPException(409, 'A posted source identity changed; use a controlled correction')
            return {'record_id': previous['record_id'], 'duplicate_source': True}
        order = self.order(session, c, p.get('order_id', '')) if kind != 'settlement.created' else None
        party = session.get(m.Record, order['party_id']) if order else None
        issued = p.get('date', '')
        try: date.fromisoformat(issued)
        except (ValueError, TypeError): raise HTTPException(422, 'Source accounting date is required')
        gateway = c['config']['gateway_bank_id']; payment = {'payment_account': 'bank', 'bank_account_id': gateway}
        if kind == 'invoice.created':
            data = {'party_id': party.id, 'party_gstin': p.get('party_gstin', party.data.get('gstin', '')),
                'party_address': p.get('billing_address', party.data.get('address', '')),
                'place_of_supply': p.get('place_of_supply', ''), 'lines': self.invoice_lines(session, c, p),
                'commerce_connection_id': c['id'], 'commerce_order_id': p['order_id'], 'commerce_source_id': external}
            company = session.get(m.Company, c['company_id']); profile = session.get(m.CompanyTaxProfile, company.id)
            calculated, amount = m.calculate(data, company, profile.mode if profile else 'regular', 'sales_invoice', session)
            if amount != decimal(p.get('amount')): raise HTTPException(422, 'Source invoice total differs from Apex line/tax calculation')
            expected_taxes = p.get('taxes', {})
            if set(expected_taxes) != {'cgst', 'sgst', 'igst'} or any(decimal(expected_taxes[h]) != decimal(calculated[h]) for h in expected_taxes):
                raise HTTPException(422, 'Source GST heads must reconcile exactly before posting')
            hold_id = order['snapshot'].get('reservation_id'); hold = None
            tracked = [line for line in calculated['lines'] if line.get('item_id') and session.get(m.Record, line['item_id']).data.get('track_stock')]
            if tracked:
                rt = self.t['reservations']; hold = self.one(session, rt, rt.c.id == hold_id, rt.c.connection_id == c['id']) if hold_id else None
                if not hold or hold['status'] != 'confirmed' or hold['order_id'] != p['order_id']: raise HTTPException(409, 'Invoice requires its confirmed order reservation')
                totals = {}
                for line in tracked: totals[line['item_id']] = totals.get(line['item_id'], Decimal(0)) + decimal(line['quantity'])
                for item_id, qty in totals.items():
                    remaining = sum((decimal(l['quantity']) - decimal(l['consumed']) for l in hold['lines'] if l['item_id'] == item_id), Decimal(0))
                    if qty > remaining: raise HTTPException(409, 'Invoice exceeds remaining reserved quantity')
            own = OWN_RESERVATION.set(hold_id)
            try: record = self.post(session, c, 'sales_invoice', party.name, issued, amount, data, 'invoice:' + external)
            finally: OWN_RESERVATION.reset(own)
            if hold:
                lines = [dict(l) for l in hold['lines']]
                for item_id, qty in totals.items():
                    for line in lines:
                        if line['item_id'] == item_id:
                            used = min(qty, decimal(line['quantity']) - decimal(line['consumed']))
                            line['consumed'] = str(decimal(line['consumed']) + used); qty -= used
                status = 'consumed' if all(decimal(l['quantity']) == decimal(l['consumed']) for l in lines) else 'confirmed'
                session.execute(update(self.t['reservations']).where(self.t['reservations'].c.id == hold_id).values(lines=lines, status=status, updated_at=now()))
            result = {'record_id': record['id'], 'invoice_number': record['number'], 'amount': record['amount']}
        elif kind == 'payment.captured':
            allocations = []
            for source in p.get('allocations', []):
                inv = self.link(session, c, 'invoice', source['invoice_id'])
                if not inv: raise HTTPException(503, 'Waiting for captured payment invoice')
                target = session.get(m.Record, inv['record_id'])
                if target.name != party.name or inv['snapshot'].get('order_id') != p['order_id']: raise HTTPException(422, 'Capture allocations must match the source order and party')
                allocations.append({'document_id': target.id, 'amount': str(decimal(source['amount'], positive=True))})
            data = {**payment, 'party_id': party.id, 'commerce_source_id': external, 'commerce_connection_id': c['id']}
            if allocations: data['allocations'] = allocations
            else: data.update(is_advance=True, advance_supply=p.get('advance_supply', 'goods'), advance_gst_rate=p.get('advance_gst_rate', '0'), place_of_supply=p.get('place_of_supply', ''))
            record = self.post(session, c, 'payment_in', party.name, issued, decimal(p['amount'], positive=True), data, 'capture:' + external)
            result = {'record_id': record['id'], 'advance': not bool(allocations)}
        elif kind == 'refund.created':
            invoice = self.link(session, c, 'invoice', p.get('invoice_id', ''))
            if not invoice: raise HTTPException(503, 'Waiting for refunded source invoice')
            source = session.get(m.Record, invoice['record_id'])
            if source.name != party.name or invoice['snapshot'].get('order_id') != p['order_id']: raise HTTPException(422, 'Return must use its source order and party')
            if not isinstance(p.get('return_received', False), bool): raise HTTPException(422, 'Return receipt option must be boolean')
            data = {'applied_to': source.id, 'return_stock': p.get('return_received', False),
                'party_id': party.id, 'party_gstin': source.data.get('party_gstin', ''),
                'place_of_supply': source.data.get('place_of_supply', ''), 'lines': self.invoice_lines(session, c, p),
                'commerce_connection_id': c['id'], 'commerce_source_id': external}
            record = self.post(session, c, 'credit_note', party.name, issued, p['amount'], data, 'credit:' + external)
            if decimal(record['amount']) != decimal(p['amount']): raise HTTPException(422, 'Source return total differs from its accounting credit')
            result = {'record_id': record['id']}
        elif kind == 'payment.refunded':
            from workflow_extensions import available_credit, post
            credit = self.link(session, c, 'credit', p.get('credit_id', ''))
            if not credit and p.get('capture_id'):
                capture = self.link(session, c, 'capture', p['capture_id'])
                if not capture: raise HTTPException(503, 'Waiting for the source advance capture')
                source = session.get(m.Record, capture['record_id'])
                if capture['snapshot'].get('order_id') != p['order_id'] or source.name != party.name or not source.data.get('is_advance'):
                    raise HTTPException(422, 'Refund must use an unapplied advance from this source order')
                key = 'commerce-advance-refund-' + hashlib.sha256((c['id'] + external).encode()).hexdigest()[:48]
                body = m.RecordInput(kind='advance_refund', name=party.name, date=issued, amount=str(decimal(p['amount'], positive=True)), data=payment)
                record = m.refund_advance_in_transaction(c['company_id'], source.id, body, SimpleNamespace(headers={'Idempotency-Key': key}), session.get(m.User, c['tenant_id']), session, commit=False)
                result = {'record_id': record['id'], 'advance_refund': True}
                self.add_link(session, c, identity, external, result['record_id'], None, event['version'], {**p, '_hash': digest(p), '_result': result})
                m.audit(session, c['company_id'], session.get(m.User, c['tenant_id']), 'commerce.payment.refunded', 'commerce', c['id'], {'source_id': external, 'record_id': result['record_id']})
                return result
            if not credit: raise HTTPException(503, 'Waiting for the source credit note')
            note = session.get(m.Record, credit['record_id']); amount = decimal(p['amount'], positive=True)
            if credit['snapshot'].get('order_id') != p['order_id'] or note.name != party.name or date.fromisoformat(issued) < note.date or amount > available_credit(m, c['company_id'], note, session):
                raise HTTPException(422, 'Refund exceeds available customer credit or has an invalid party/date')
            key = 'commerce-refund-' + hashlib.sha256((c['id'] + external).encode()).hexdigest()[:48]
            body = m.RecordInput(kind='customer_refund', name=party.name, date=issued, amount=str(amount), data={})
            record_obj = post(m, c['company_id'], session.get(m.User, c['tenant_id']), session, body, 'customer_refund', party.name,
                {**payment, 'credit_note_id': note.id, 'party_id': party.id}, [('customer_credits', amount, Decimal(0)), (m.payment_key(payment), Decimal(0), amount)], key, digest(p))
            result = {'record_id': record_obj.id}
        elif kind == 'return.received':
            from commerce_returns import receive
            result = receive(self, session, c, p, party, external, issued)
        elif kind == 'settlement.created':
            destination = str(p.get('bank_account_id', ''))
            m.bank_account_for(c['company_id'], destination, session)
            if not destination or destination == gateway: raise HTTPException(422, 'Choose a different company bank account for settlement')
            gross, net, fee = (m.money(decimal(p[key])) for key in ('gross', 'net', 'fee'))
            refund_ids = p.get('refund_ids', [])
            if len(refund_ids) != len(set(refund_ids)): raise HTTPException(422, 'Choose each settlement refund exactly once')
            refund_total = Decimal(0)
            for refund_id in refund_ids:
                refund = self.link(session, c, 'refund', refund_id)
                if not refund: raise HTTPException(503, 'Waiting for settlement refund')
                if refund['snapshot'].get('_settled'): raise HTTPException(409, 'Refund is already included in a settlement')
                refund_total += session.get(m.Record, refund['record_id']).amount
            if gross != net + fee + refund_total or gross <= 0 or net <= 0 or decimal(p.get('fee_gst', 0)):
                raise HTTPException(422, 'Settlement gross minus refunds and fee must equal bank net; supplier GST fees need separate reviewed bills')
            capture_ids = p.get('capture_ids', [])
            if not capture_ids or len(capture_ids) != len(set(capture_ids)): raise HTTPException(422, 'Choose each settlement capture exactly once')
            capture_total = Decimal(0)
            for capture_id in p.get('capture_ids', []):
                capture = self.link(session, c, 'capture', capture_id)
                if not capture: raise HTTPException(503, 'Waiting for settlement capture')
                if capture['snapshot'].get('_settled'): raise HTTPException(409, 'Capture is already included in a settlement')
                capture_total += session.get(m.Record, capture['record_id']).amount
            if capture_total != gross: raise HTTPException(422, 'Settlement captures do not reconcile to gross')
            expense = self.post(session, c, 'expense', 'Gateway settlement fees', issued, fee, {**payment, 'category': 'Payment gateway fees'}, 'settlement-fee:' + external) if fee else None
            transfer = self.post(session, c, 'bank_transfer', 'Gateway settlement', issued, net,
                {'direction': 'bank_to_bank', 'bank_account_id': gateway, 'to_bank_account_id': destination}, 'settlement:' + external)
            for capture_id in p['capture_ids']:
                capture = self.link(session, c, 'capture', capture_id)
                self.add_link(session, c, 'capture', capture_id, capture['record_id'], None, capture['version'], {**capture['snapshot'], '_settled': external})
            for refund_id in refund_ids:
                refund = self.link(session, c, 'refund', refund_id)
                self.add_link(session, c, 'refund', refund_id, refund['record_id'], None, refund['version'], {**refund['snapshot'], '_settled': external})
            result = {'record_id': transfer['id'], 'fee_record_id': expense['id'] if expense else None}
        else: raise HTTPException(422, 'This source action requires a reviewed adapter before automatic posting')
        self.add_link(session, c, identity, external, result['record_id'], None, event['version'], {**p, '_hash': digest(p), '_result': result})
        if kind in ('invoice.created', 'payment.captured'): self.apply_order_advances(session, c, p['order_id'])
        m.audit(session, c['company_id'], session.get(m.User, c['tenant_id']), 'commerce.' + kind, 'commerce', c['id'], {'source_id': external, 'record_id': result['record_id']})
        return result

def install(app, m):
    service = Commerce(m); m.commerce = service
    m.commerce_assert_available = service.assert_available
    m.commerce_stock_changed = service.stock_changed
    root = '/api/companies/{company_id}/commerce'
    def company(cid, user, session, owner=False, write=False):
        c = m.lock_company(cid, user, session) if owner or write else m.company_for(cid, user, session)
        if owner and c.owner_id != user.id: raise HTTPException(403, 'Only the company owner can configure store connections')
        if write: m.require_write(c, user, session)
        return c
    @app.get(root + '/connections')
    def connections(company_id: str, user=Depends(m.current_user), session: Session=Depends(m.db)):
        c = company(company_id, user, session); t = service.t['connections']
        return [service.public_connection(row) for row in session.execute(select(t).where(t.c.company_id == c.id, t.c.tenant_id == c.owner_id).order_by(t.c.name)).mappings()]
    @app.post(root + '/connections', status_code=201)
    def connect(company_id: str, body: ConnectionInput, user=Depends(m.current_user), session: Session=Depends(m.db)):
        c = company(company_id, user, session, owner=True)
        if body.currency != 'INR': raise HTTPException(422, 'This accounting profile currently requires INR base currency')
        base = validate_url(body.base_url); m.bank_account_for(c.id, body.gateway_bank_id, session)
        token = secrets.token_urlsafe(32); stamp = now()
        row = dict(id=str(uuid4()), tenant_id=c.owner_id, company_id=c.id, name=body.name.strip(), base_url=base,
            channel=body.channel, currency=body.currency, secret=cipher().encrypt(token.encode()).decode(), status='draft',
            config={'gateway_bank_id': body.gateway_bank_id, 'verified': False}, version=1, created_at=stamp, updated_at=stamp)
        if not row['name']: raise HTTPException(422, 'Enter a store name')
        try:
            session.execute(insert(service.t['connections']).values(**row)); m.audit(session, c.id, user, 'commerce.connection_created', 'commerce', row['id']); session.commit()
        except IntegrityError:
            session.rollback(); raise HTTPException(409, 'This store channel is already connected; a channel can belong to only one company')
        return {**service.public_connection(row), 'setup_secret': token, 'setup_note': 'Shown once. Configure ApexBridge with this connection ID and secret; never embed it in a client app.'}
    @app.post(root + '/connections/{connection_id}/verify')
    def verify(company_id: str, connection_id: str, user=Depends(m.current_user), session: Session=Depends(m.db)):
        c = service.scoped(session, company(company_id, user, session, owner=True), connection_id)
        result = remote(service, c, 'GET', '/apex-bridge/v1/capabilities')
        if result.get('protocol') != 1 or str(result.get('channel')) != c['channel'] or result.get('currency') != c['currency']:
            raise HTTPException(409, 'Store protocol, channel or base currency does not match')
        config = {**c['config'], 'verified': True, 'capabilities': result}
        session.execute(update(service.t['connections']).where(service.t['connections'].c.id == c['id']).values(config=config, updated_at=now())); session.commit()
        return {'verified': True, 'capabilities': result}
    @app.put(root + '/connections/{connection_id}/state')
    def state(company_id: str, connection_id: str, body: ConnectionState, user=Depends(m.current_user), session: Session=Depends(m.db)):
        co = company(company_id, user, session, owner=True); c = service.scoped(session, co, connection_id)
        if body.status == 'active' and not c['config'].get('verified'): raise HTTPException(409, 'Verify the installed bridge before activation')
        if body.status == 'active':
            referenced=set(session.scalars(select(m.Record.data['commerce_connection_id'].as_string()).where(m.Record.company_id==company_id)).all())-{None,''}
            connected=set(session.scalars(select(service.t['connections'].c.id).where(service.t['connections'].c.company_id==company_id)).all())
            if referenced-connected:raise HTTPException(409, 'Restored commerce postings need source identity reconciliation before live activation. Restore the full database or review the original source mappings first.')
        if c['status'] == body.status: return service.public_connection(c)
        session.execute(update(service.t['connections']).where(service.t['connections'].c.id == c['id']).values(status=body.status, updated_at=now()))
        if body.status == 'active': service.stock_changed(company_id, session)
        m.audit(session, co.id, user, 'commerce.' + body.status, 'commerce', connection_id); session.commit()
        return service.public_connection(service.scoped(session, co, connection_id))
    @app.get(root + '/connections/{connection_id}/workspace')
    def workspace(company_id: str, connection_id: str, user=Depends(m.current_user), session: Session=Depends(m.db)):
        c = service.scoped(session, company(company_id, user, session), connection_id)
        result = {'connection': service.public_connection(c), 'stock': service.stocks(session, c)}
        for key in ('links', 'orders', 'reservations', 'inbox', 'outbox', 'reconciliations'):
            t = service.t[key]; query = select(t).where(t.c.connection_id == c['id'], t.c.company_id == company_id)
            if 'created_at' in t.c: query = query.order_by(t.c.created_at.desc())
            result[key] = [dict(r) for r in session.execute(query.limit(200)).mappings()]
        result['summary'] = {key: {status: session.scalar(select(func.count()).select_from(service.t[key]).where(service.t[key].c.connection_id == c['id'], service.t[key].c.status == status))
            for status in ('pending', 'processing', 'done', 'review', 'retry')} for key in ('inbox', 'outbox')}
        return result
    @app.post(root + '/connections/{connection_id}/links')
    def link(company_id: str, connection_id: str, body: LinkInput, user=Depends(m.current_user), session: Session=Depends(m.db)):
        co = company(company_id, user, session, write=True); c = service.scoped(session, co, connection_id)
        item = session.scalar(select(m.Record).where(m.Record.company_id == company_id, m.Record.id == body.record_id,
            m.Record.kind == ('item' if body.entity_type == 'product' else 'party')))
        if not item: raise HTTPException(422, 'Choose a matching record in this company')
        existing = service.link(session, c, body.entity_type, body.external_id)
        if existing and existing['record_id'] != item.id: raise HTTPException(409, 'Existing source mappings cannot be reassigned silently')
        if body.entity_type == 'product' and not (body.sku or '').strip(): raise HTTPException(422, 'A unique SKU is required')
        try:
            service.add_link(session, c, body.entity_type, body.external_id, item.id, body.sku or None)
            m.audit(session, co.id, user, 'commerce.mapping_saved', 'commerce', connection_id)
            service.stock_changed(company_id, session); session.commit()
        except IntegrityError:
            session.rollback(); raise HTTPException(409, 'SKU or external identity is already mapped')
        return {'mapped': True}
    @app.post(root + '/connections/{connection_id}/commands', status_code=202)
    def command(company_id: str, connection_id: str, body: CommandInput, user=Depends(m.current_user), session: Session=Depends(m.db)):
        c = service.scoped(session, company(company_id, user, session, write=True), connection_id)
        if any(str(key).startswith('_') for key in body.payload): raise HTTPException(422, 'Reserved command fields are not accepted')
        if c['status'] != 'active': raise HTTPException(409, 'Activate the connection before sending commands')
        row = service.enqueue(session, c, body.command_id, body.operation, body.payload); session.commit(); return row
    @app.post(root + '/connections/{connection_id}/retry/{direction}/{message_id}')
    def retry(company_id: str, connection_id: str, direction: str, message_id: str, user=Depends(m.current_user), session: Session=Depends(m.db)):
        c = service.scoped(session, company(company_id, user, session, write=True), connection_id)
        if direction not in ('inbox', 'outbox'): raise HTTPException(404, 'Message not found')
        t = service.t[direction]; row = service.one(session, t, t.c.connection_id == c['id'], t.c.id == message_id)
        if not row: raise HTTPException(404, 'Message not found')
        if row['status'] not in ('review', 'retry'): raise HTTPException(409, 'Only failed messages can be retried')
        session.execute(update(t).where(t.c.id == message_id).values(status='pending', available_at=now(), lease_until=None, error='')); session.commit()
        return {'status': 'pending'}
    @app.get('/api/internal/commerce/drain', include_in_schema=False)
    def scheduled_delivery(request: Request):
        secret = os.getenv('CRON_SECRET', '')
        if not secret: raise HTTPException(503, 'Scheduled delivery is not configured')
        if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + secret):
            raise HTTPException(401, 'Invalid scheduler authorization')
        from commerce_worker import process_one
        deadline = time.monotonic() + 20
        count = 0
        while count < 40 and time.monotonic() < deadline:
            progressed = False
            for direction in ('inbox', 'outbox'):
                if time.monotonic() >= deadline: break
                if process_one(direction): count += 1; progressed = True
            if not progressed: break
        return {'processed': count}

    @app.post('/api/integrations/bagisto/{connection_id}/events', status_code=202)
    async def events(connection_id: str, request: Request, session: Session=Depends(m.db)):
        raw = await request.body()
        if len(raw) > 1_000_000: raise HTTPException(413, 'Event too large')
        c = service.service(session, connection_id, request, raw)
        try: body = EventInput.model_validate_json(raw)
        except ValueError: raise HTTPException(422, 'Invalid integration event schema')
        row = service.ingest(session, c, body); session.commit()
        return {'id': row['id'], 'status': row['status'], 'result': row['result']}
    @app.post('/api/integrations/bagisto/{connection_id}/reservations')
    async def reservations(connection_id: str, request: Request, session: Session=Depends(m.db)):
        raw = await request.body(); c = service.service(session, connection_id, request, raw)
        try: body = ReserveInput.model_validate_json(raw)
        except ValueError: raise HTTPException(422, 'Invalid reservation schema')
        row = service.reserve(session, c, body)
        availability = {}
        for line in body.lines:
            link = service.link(session, c, 'product', line.external_product_id)
            availability[line.external_product_id] = str(max(Decimal(0), service.available(session, c['company_id'], link['record_id'])))
        session.commit(); return {**row, 'availability': availability}
    @app.post('/api/integrations/bagisto/{connection_id}/reservations/{reservation_id}')
    async def reservation_action(connection_id: str, reservation_id: str, request: Request, session: Session=Depends(m.db)):
        raw = await request.body(); c = service.service(session, connection_id, request, raw)
        try: body = ReservationAction.model_validate_json(raw)
        except ValueError: raise HTTPException(422, 'Invalid reservation action')
        row = service.reservation_action(session, c, reservation_id, body); session.commit(); return row

def remote(service, c, method, path, payload=None):
    base = validate_url(c['base_url']); body = encode(payload) if payload is not None else b''; stamp = str(int(time.time()))
    headers = {'X-Apex-Connection': c['id'], 'X-Apex-Timestamp': stamp,
        'X-Apex-Signature': signature(service.secret(c), stamp, method, path, body), 'Content-Type': 'application/json', 'Accept': 'application/json'}
    try:
        with httpx.Client(timeout=25, follow_redirects=False, trust_env=False) as client:
            response = client.request(method, base + path, content=body, headers=headers)
        if response.status_code >= 500 or response.status_code == 429: raise HTTPException(503, 'Store is temporarily unavailable')
        if response.status_code not in range(200, 300): raise HTTPException(409, 'Store rejected the integration request; check bridge configuration and review the action')
        result = response.json()
        if not isinstance(result, dict): raise ValueError()
        return result
    except (httpx.HTTPError, ValueError): raise HTTPException(503, 'Cannot reach the configured Bagisto bridge')
