import hashlib
import json
import re
from accounting import audit, audit_changes, company_for, current_user, db, lock_company, money, obj
from datetime import date as DateType
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from gst_identifiers import require_gstin
from inventory_setup import EXTRA_KEYS, clean_item_extras
from models import MasterImportReceipt, Record, RecordPosting, StockMovement, User
from pydantic import BaseModel, Field, ValidationError
from schemas import MasterImport, MasterRow, validate_item_image, validate_master_defaults
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import uuid4
from vyapar_audit import transaction_audit
from vyapar_import import inspect_backup, master_candidates
from vyapar_migration import migrate as migrate_vyapar


router = APIRouter()


class VyaparImportInput(BaseModel):
    backup_base64: str = Field(max_length=4_000_000)
    digest: str = ''


@router.post('/api/companies/{company_id}/imports/vyapar-posting/{action}')
def vyapar_full_posting(company_id: str, action: str, body: VyaparImportInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can migrate a backup')
    if action not in {'preview', 'commit'}: raise HTTPException(404, 'Unknown migration action')
    try:
        backup = inspect_backup(body.backup_base64)
        return migrate_vyapar(company, user, session, backup, action, body.digest)
    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
        session.rollback()
        raise HTTPException(422, 'Unsupported source data; migration was not posted') from exc


@router.get('/api/companies/{company_id}/imports/vyapar-posting/reconciliation')
def vyapar_reconciliation(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can view the migration reconciliation')
    archive = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'vyapar_backup_archive'))
    if not archive or archive.data.get('scope') != 'full_posting': raise HTTPException(404, 'No posted migration found')
    return archive.data['posting_summary']


@router.post('/api/companies/{company_id}/imports/vyapar/{action}')
def vyapar_import(company_id: str, action: str, body: VyaparImportInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can import a backup')
    if action not in {'preview', 'commit'}: raise HTTPException(404, 'Import action not found')
    try: backup = inspect_backup(body.backup_base64)
    except ValueError as exc: raise HTTPException(422, str(exc))
    tables, digest = backup['tables'], backup['digest']
    archives = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.kind == 'vyapar_backup_archive')))
    existing = next((r for r in archives if r.data.get('digest') == digest), None)
    if existing: return {'already_imported': True, 'digest': digest, 'archive_id': existing.id, 'counts': backup['counts'],
        'mapping_audit': transaction_audit(tables), 'archive_missing_tables': [name for name in tables if name not in existing.data.get('tables', {})]}
    if archives: raise HTTPException(409, 'This company already has a different Vyapar backup; use a separate company for another backup')
    if session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id)):
        raise HTTPException(409, 'Use a company without posted accounting entries for backup migration')
    names = {(r.kind, r.name.strip().casefold()) for r in session.scalars(select(Record).where(Record.company_id == company_id, Record.kind.in_(['party', 'item'])))}
    errors, ready, skipped = [], [], []
    for kind, source_id, values, original in master_candidates(tables):
        try:
            values['name'] = values['name'].strip()
            if kind == 'item':
                for key in ('sale_rate', 'purchase_rate', 'gst_rate'): values[key] = str(money(Decimal(str(values[key]))))
            row = MasterRow.model_validate(values)
            if not row.name: raise ValueError('Name is empty')
            if row.gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}', row.gstin.upper()): raise ValueError('Invalid GSTIN')
            if row.email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', row.email): raise ValueError('Invalid email')
            identity = (kind, row.name.casefold())
            if identity in names:
                skipped.append({'kind': kind, 'source_id': source_id, 'name': row.name}); continue
            names.add(identity)
            ready.append((kind, source_id, row, original))
        except (ValidationError, ValueError, InvalidOperation):
            errors.append({'kind': kind, 'source_id': source_id, 'name': str(values.get('name', ''))[:120], 'error': 'Check name length, contact fields, GSTIN and numeric values in the source backup'})
    report = {'digest': digest, 'company_name': str(tables['kb_firms'][0].get('firm_name') or ''), 'counts': backup['counts'],
        'mapping_audit': transaction_audit(tables),
        'ready': {'parties': sum(kind == 'party' for kind, *_ in ready), 'items': sum(kind == 'item' for kind, *_ in ready)},
        'skipped_duplicates': skipped, 'errors': errors,
        'scope': 'masters_and_source_archive', 'warnings': ['Transactions, links, opening balances and stock quantities are retained in a source archive. They do not post journals, stock movements or tax returns.', 'Expense categories remain in the archive; imported parties are marked customer and supplier.', 'Master prices are rounded to two decimals; original values are preserved. Stock tracking is disabled until opening stock is reviewed.', 'Images, attachments, app settings and user accounts are not imported.']}
    if action == 'preview': return report
    if body.digest != digest: raise HTTPException(409, 'Preview this exact backup before importing')
    if errors: raise HTTPException(422, 'Correct the preview errors before importing')
    for kind, source_id, row, original in ready:
        data = row.model_dump(mode='json', exclude={'name'})
        data.update({'vyapar_source_id': source_id, 'vyapar_source': original, 'gstin': row.gstin.upper()})
        session.add(Record(company_id=company_id, kind=kind, name=row.name, amount=Decimal('0'), date=DateType.today(), data=data))
    archive = Record(company_id=company_id, kind='vyapar_backup_archive', name=report['company_name'][:120], date=DateType.today(), amount=Decimal('0'),
        data={'digest': digest, 'archive_version': 2, 'scope': report['scope'], 'tables': tables, 'summary': report})
    session.add(archive); session.flush()
    audit(session, company_id, user, 'vyapar.imported', 'vyapar_backup_archive', archive.id, {'digest': digest, 'counts': report['ready']})
    session.commit()
    return {**report, 'archive_id': archive.id, 'imported': True}


@router.get('/api/companies/{company_id}/imports/vyapar/archive.json')
def vyapar_archive(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can export the source archive')
    archive = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'vyapar_backup_archive'))
    if not archive: raise HTTPException(404, 'No Vyapar archive imported')
    return Response(json.dumps(archive.data, ensure_ascii=False), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="vyapar-source-archive.json"'})


@router.post('/api/companies/{company_id}/masters/import', openapi_extra={
    'parameters': [{'name': 'Idempotency-Key', 'in': 'header', 'required': False,
        'schema': {'type': 'string', 'minLength': 1, 'maxLength': 80, 'pattern': '^[A-Za-z0-9._:-]+$'},
        'description': 'Optional durable operation key for dry_run=false. Matching actor and payload replay the original receipt; changed actor or payload conflicts. Preview ignores this header. Omitted keys retain legacy name-skip behavior.'}]
})
def import_masters(company_id: str, body: MasterImport, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    if body.kind not in {'party', 'item'}: raise HTTPException(422, 'Import supports parties and items only')
    import_key = request.headers.get('Idempotency-Key') if not body.dry_run else None
    fingerprint = None
    if import_key is not None:
        if not re.fullmatch(r'[A-Za-z0-9._:-]{1,80}', import_key): raise HTTPException(422, 'Use an idempotency key of 1 to 80 letters, digits, dots, underscores, colons or hyphens')
        canonical = {'operation': 'master-import-v1', 'body': body.model_dump(mode='json')}
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        receipt = session.scalar(select(MasterImportReceipt).where(MasterImportReceipt.company_id == company_id, MasterImportReceipt.operation_key == import_key))
        if receipt:
            if receipt.actor_id != user.id or receipt.request_hash != fingerprint:
                raise HTTPException(409, 'Import key belongs to a different actor or request')
            return receipt.response

    existing = {r.name.strip().casefold() for r in session.scalars(select(Record).where(Record.company_id == company_id, Record.kind == body.kind))}
    seen = set()
    errors, ready, duplicates = [], [], 0
    for index, row in enumerate(body.rows, 2):
        name = row.name.strip()
        key = name.casefold()
        if not key:
            errors.append({'row': index, 'message': 'Name is required'}); continue
        if key in existing or key in seen:
            duplicates += 1; continue
        try:
            validate_master_defaults(row, body.kind)
            if body.kind == 'item':validate_item_image(row)
        except HTTPException as exc:
            errors.append({'row': index, 'message': exc.detail});continue
        data = row.model_dump(mode='json', exclude={'name'})
        if body.kind == 'party':
            if row.party_type not in {'customer', 'supplier', 'both'}:
                errors.append({'row': index, 'message': 'Party type must be customer, supplier or both'}); continue
            try:require_gstin(row.gstin, 'Party GSTIN')
            except HTTPException as exc:
                errors.append({'row': index, 'message': exc.detail});continue
            if row.email.strip() and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', row.email.strip()):
                errors.append({'row': index, 'message': 'Enter a valid email'}); continue
            data = {'party_type': row.party_type, 'gstin': row.gstin.strip().upper(), 'address': row.address, 'phone': row.phone.strip(), 'email': row.email.strip(), 'payment_terms_days': row.payment_terms_days, 'credit_limit':str(row.credit_limit) if row.credit_limit is not None else None, 'is_active':row.is_active, 'shipping_address':row.shipping_address}
        else:
            data = {key: data[key] for key in ('hsn', 'unit', 'sale_rate', 'purchase_rate', 'gst_rate', 'track_stock','barcode','item_type','tax_treatment','image_data_url','image_thumbnail','low_stock_threshold','is_active')}
        seen.add(key)
        ready.append((name, data))
    result = {'dry_run': body.dry_run, 'ready': len(ready), 'duplicates': duplicates, 'errors': errors}
    if body.dry_run: return result
    if errors: raise HTTPException(422, {'message': 'Resolve import errors before saving', **result})
    created = [Record(id=str(uuid4()), company_id=company_id, kind=body.kind, name=name, data=data) for name, data in ready]
    session.add_all(created)
    response = {**result, 'created': len(ready)}
    if import_key is not None:
        response = {**response, 'operation_key': import_key, 'record_ids': [record.id for record in created]}
        session.add(MasterImportReceipt(company_id=company_id, actor_id=user.id, operation_key=import_key, request_hash=fingerprint, response=response))
    audit(session, company_id, user, 'masters.imported', body.kind, company_id, {'created': len(ready), 'duplicates': duplicates})
    session.commit()
    return response


@router.get('/api/companies/{company_id}/masters/import-receipts/{operation_key}')
def master_import_receipt(company_id: str, operation_key: str, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    receipt = session.scalar(select(MasterImportReceipt).where(MasterImportReceipt.company_id == company_id, MasterImportReceipt.operation_key == operation_key, MasterImportReceipt.actor_id == user.id))
    if not receipt: raise HTTPException(404, 'No committed import receipt found. This does not prove an in-flight request failed; do not start a new import.')
    return receipt.response


@router.put('/api/companies/{company_id}/masters/{master_id}')
def update_master(company_id: str, master_id: str, body: MasterRow,
                  user: User = Depends(current_user), session: Session = Depends(db)):
    import book_services as services
    lock_company(company_id, user, session)
    validate_item_image(body)
    master = session.scalar(select(Record).where(Record.company_id == company_id,
        Record.id == master_id, Record.kind.in_(['party', 'item'])))
    if not master: raise HTTPException(404, 'Party or item not found')
    before = dict(master.data or {})
    validate_master_defaults(body, master.kind, previous=before)
    sent_extras = {k: v for k, v in body.model_dump(mode='json').items() if k in EXTRA_KEYS and k in body.model_fields_set}
    extras = clean_item_extras(services, company_id, master.kind, sent_extras, before, session)
    # New metadata omitted by an older client is retained, not implicitly cleared.
    # Validate that retained threshold against the proposed classification too.
    if master.kind == 'item' and 'low_stock_threshold' not in body.model_fields_set and (master.data or {}).get('low_stock_threshold') is not None and (not body.track_stock or body.item_type != 'goods'):
        raise HTTPException(422, 'Clear the low-stock threshold explicitly before changing this item classification')
    if body.name.strip() != master.name: raise HTTPException(422, 'Names cannot be changed after creation')
    if master.kind == 'party':
        if body.party_type not in {'customer', 'supplier', 'both'}: raise HTTPException(422, 'Choose a valid party type')
        require_gstin(body.gstin, 'Party GSTIN', unchanged=before.get('gstin',''))
        if body.email.strip() and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', body.email.strip()): raise HTTPException(422, 'Enter a valid email')
        master.data = {**(master.data or {}), 'party_type': body.party_type, 'gstin': body.gstin.strip().upper(), 'address': body.address,
                       'phone': body.phone.strip(), 'email': body.email.strip()}
        if 'payment_terms_days' in body.model_fields_set:master.data={**master.data,'payment_terms_days':body.payment_terms_days}
        if 'credit_limit' in body.model_fields_set:master.data={**master.data,'credit_limit':str(body.credit_limit) if body.credit_limit is not None else None}
    else:
        if body.track_stock != bool(master.data.get('track_stock', False)):
            raise HTTPException(422, 'Stock tracking cannot be changed after item creation')
        if body.item_type != master.data.get('item_type', 'goods') and body.track_stock and session.scalar(select(StockMovement.id).where(StockMovement.company_id == company_id, StockMovement.item_id == master.id).limit(1)):
            raise HTTPException(422, 'Item classification cannot change after stock history; create a separate item instead')
        values = body.model_dump(mode='json')
        master.data = {**(master.data or {}), **{key: values[key] for key in ('hsn', 'unit', 'sale_rate', 'purchase_rate', 'gst_rate', 'track_stock','barcode','item_type','tax_treatment','image_data_url','image_thumbnail','low_stock_threshold') if key not in {'image_data_url','image_thumbnail','low_stock_threshold'} or key in body.model_fields_set}}
    if extras: master.data = {**master.data, **extras}
    for field in ('is_active','shipping_address'):
        if field in body.model_fields_set and (field != 'shipping_address' or master.kind == 'party'):
            master.data={**master.data,field:getattr(body,field)}
    audit(session, company_id, user, 'master.updated', master.kind, master.id, audit_changes(before, master.data))
    if master.kind == 'item' and hasattr(services, 'commerce_stock_changed'): services.commerce_stock_changed(company_id, session)
    session.commit(); session.refresh(master)
    return obj(master)


@router.get('/api/companies/{company_id}/masters/export.{fmt}')
def export_masters(company_id: str, fmt: str, kind: str,
                   user: User = Depends(current_user), session: Session = Depends(db)):
    from routers.reports import export_table
    import book_services as services
    company = company_for(company_id, user, session)
    if kind not in {'party', 'item'}: raise HTTPException(422, 'Choose parties or items')
    masters = list(session.scalars(select(Record).where(Record.company_id == company_id,
        Record.kind == kind).order_by(Record.name, Record.id)))
    if kind == 'party':
        headers = ['Name', 'Type', 'GSTIN', 'Phone', 'Email', 'Address']
        rows = [[r.name, r.data.get('party_type', 'both'), r.data.get('gstin', ''),
                 r.data.get('phone', ''), r.data.get('email', ''), r.data.get('address', '')] for r in masters]
    else:
        headers = ['Name', 'HSN / SAC', 'Unit', 'Sale rate', 'Purchase rate', 'GST rate', 'Stock tracked','Barcode','Item type','Tax treatment']
        rows = [[r.name, r.data.get('hsn', ''), r.data.get('unit', ''), r.data.get('sale_rate', '0'),
                 r.data.get('purchase_rate', '0'), r.data.get('gst_rate', '0'), 'Yes' if r.data.get('track_stock') else 'No',r.data.get('barcode',''),r.data.get('item_type','goods'),r.data.get('tax_treatment','taxable' if Decimal(str(r.data.get('gst_rate',0))) else 'nil_rated')] for r in masters]
    if kind == 'item':
        from inventory_setup import export_columns
        extra_headers, extra_cells = export_columns(services, company_id, session)
        headers = headers + extra_headers; rows = [row + extra_cells(r) for row, r in zip(rows, masters)]
    return export_table(company.name, 'Party list' if kind == 'party' else 'Item list', headers, rows, fmt, kind + '-list')
