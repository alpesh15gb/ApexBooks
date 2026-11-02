"""Read bounded Vyapar ZIP/SQLite backups without executing backup SQL."""
import base64
import binascii
import hashlib
import io
import json
import sqlite3
import zipfile

TABLES = ('kb_firms', 'kb_names', 'kb_items', 'kb_tax_code', 'kb_item_units',
          'kb_transactions', 'kb_lineitems', 'kb_txn_links', 'kb_paymentTypes',
          'txn_payment_mapping', 'kb_item_adjustments', 'kb_linked_transactions',
          'kb_closed_link_txn_table', 'kb_item_units_mapping', 'kb_prefix',
          'kb_tax_mapping', 'other_accounts', 'chart_of_accounts_mapping',
          'journal_entry', 'journal_entry_line_items', 'kb_cash_adjustments',
          'kb_item_stock_tracking', 'loan_accounts', 'loan_transactions',
          'store_transactions', 'store_line_items', 'kb_bank_adjustments',
          'party_to_party_transfer', 'kb_address', 'kb_extra_charges',
          'terms_and_conditions', 'tnc_txn_type_mapping')

def inspect_backup(encoded):
    if len(encoded) > 4_000_000: raise ValueError('Backup exceeds 3 MB')
    try: raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error): raise ValueError('Invalid backup encoding')
    if len(raw) > 3_000_000: raise ValueError('Backup exceeds 3 MB')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            if len(files) != 1 or not files[0].filename.lower().endswith('.vyp'):
                raise ValueError('Expected a Vyapar backup with one .vyp database')
            entry = files[0]
            if entry.flag_bits & 1: raise ValueError('Encrypted backups are not supported')
            if entry.file_size > 50_000_000 or entry.file_size > max(entry.compress_size, 1) * 200:
                raise ValueError('Expanded backup exceeds the supported limit')
            with archive.open(entry) as stream: database = stream.read(50_000_001)
    except (zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError):
        raise ValueError('This file is not a supported Vyapar backup')
    if not database.startswith(b'SQLite format 3\x00') or len(database) > 50_000_000:
        raise ValueError('Backup database is invalid')
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    try:
        connection.deserialize(database)
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA query_only=ON')
        budget = [0]
        def progress():
            budget[0] += 1
            return int(budget[0] > 20000)
        connection.set_progress_handler(progress, 1000)
        schema = dict(connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
        if not {'kb_firms', 'kb_names', 'kb_items', 'kb_transactions'}.issubset(schema):
            raise ValueError('Unsupported Vyapar database schema')
        tables = {}
        for name in TABLES:
            if name not in schema: tables[name] = []; continue
            if not (schema[name] or '').upper().startswith('CREATE TABLE'):
                raise ValueError('Unsupported database table')
            rows = connection.execute('SELECT * FROM "' + name + '" LIMIT 10001').fetchall()
            if len(rows) > 10000: raise ValueError('A backup table exceeds 10,000 records')
            tables[name] = [{key: value for key, value in dict(row).items() if not isinstance(value, bytes)} for row in rows]
        if len(tables['kb_firms']) != 1: raise ValueError('Import currently requires a single-company backup')
        if len(json.dumps(tables, ensure_ascii=False, allow_nan=False).encode()) > 3_000_000:
            raise ValueError('Normalized source archive exceeds 3 MB; split the migration before importing')
        return {'digest': hashlib.sha256(raw).hexdigest(), 'tables': tables,
                'counts': {name: len(rows) for name, rows in tables.items()}}
    except (sqlite3.Error, OverflowError): raise ValueError('Backup database is damaged or unsupported')
    finally: connection.close()

def master_candidates(tables):
    tax = {r['tax_code_id']: r for r in tables['kb_tax_code']}
    units = {r['unit_id']: r.get('unit_short_name') or r.get('unit_name', '') for r in tables.get('kb_item_units',[])}
    candidates = []
    for row in tables['kb_names']:
        if row.get('name_type') != 1: continue  # expense categories are not parties
        candidates.append(('party', row['name_id'], {'name': row.get('full_name') or '', 'party_type': 'both',
            'phone': row.get('phone_number') or '', 'email': row.get('email') or '',
            'address': row.get('address') or '', 'gstin': row.get('name_gstin_number') or ''}, row))
    for row in tables['kb_items']:
        code = tax.get(row.get('item_tax_id'), {})
        rate = code.get('tax_rate') or 0
        if str(code.get('tax_code_name', '')).startswith(('SGST', 'CGST')): rate *= 2
        candidates.append(('item', row['item_id'], {'name': row.get('item_name') or '',
            'hsn': row.get('item_hsn_sac_code') or '', 'unit': units.get(row.get('base_unit_id'), ''),
            'sale_rate': row.get('item_sale_unit_price') or 0, 'purchase_rate': row.get('item_purchase_unit_price') or 0,
            'gst_rate': rate, 'item_type':'services' if row.get('item_type')==3 else 'goods', 'track_stock': False}, row))
    return candidates

def canonical_master_names(candidates):
    """Bound display identities without conflating same-prefix source masters.

    Source IDs remain the real identity. Full names stay in vyapar_source.
    Reserve unambiguous short names first so generated suffixes cannot collide
    with an existing literal source name (including case/whitespace variants).
    """
    from collections import Counter
    counts=Counter((kind,str(values['name']).strip().casefold()) for kind,_,values,_ in candidates)
    result={};used=set();pending=[]
    for kind,sid,values,_ in candidates:
        raw=str(values['name']).strip();key=(kind,raw.casefold())
        if len(raw)<=120 and counts[key]==1:
            result[(kind,sid)]=raw;used.add(key)
        else:pending.append((kind,sid,raw))
    for kind,sid,raw in sorted(pending,key=lambda row:(row[0],str(row[1]))):
        counter=0
        while True:
            suffix=f' [VYP-{sid}'+(f'-{counter}' if counter else '')+']'
            name=raw[:120-len(suffix)]+suffix
            if (kind,name.casefold()) not in used:break
            counter+=1
        result[(kind,sid)]=name;used.add((kind,name.casefold()))
    return result
