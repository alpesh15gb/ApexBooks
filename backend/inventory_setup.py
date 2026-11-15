"""Per-company inventory setup: item locations, the optional Automobile module and its vehicle list.

Stored as one `inventory_setup` record per company, so it travels with company backups like other settings records.
Item locations are referenced by id, so the owner can rename a location (or reorganise a shop) without touching items.
"""
from datetime import date as DateType
from typing import Literal
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from vehicle_catalog import CATALOG, CATALOG_VERSION, VEHICLE_TYPES

KIND = 'inventory_setup'
LOCATION_ITEM_LIMIT = 5
EXTRA_KEYS = ('location_ids', 'vehicle_fitment', 'oem_number', 'part_brand', 'part_grade')
AUTOMOBILE_KEYS = ('vehicle_fitment', 'oem_number', 'part_brand', 'part_grade')
PART_GRADES = {'', 'oem', 'aftermarket', 'used', 'refurbished'}
VehicleType = Literal['car', 'two_wheeler', 'commercial', 'three_wheeler']


def tidy(text):
    return ' '.join(str(text or '').split())


def key(text):
    return tidy(text).casefold()


class LocationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=40)
    active: bool = Field(default=True, strict=True)


class AddedMake(BaseModel):
    model_config = ConfigDict(extra='forbid')
    make: str = Field(min_length=1, max_length=40)
    type: VehicleType = 'car'
    models: list[str] = Field(default_factory=list, max_length=400)


class HiddenModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    make: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=60)


class SetupIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0, strict=True)
    automobile_enabled: bool = Field(strict=True)
    locations: list[LocationIn] = Field(default_factory=list, max_length=300)
    vehicle_added: list[AddedMake] = Field(default_factory=list, max_length=300)
    vehicle_hidden_makes: list[str] = Field(default_factory=list, max_length=300)
    vehicle_hidden_models: list[HiddenModel] = Field(default_factory=list, max_length=3000)


class FitmentIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    make: str = Field(min_length=1, max_length=40)
    model: str = Field(default='', max_length=60)
    year_from: int | None = Field(default=None, ge=1950, le=2100, strict=True)
    year_to: int | None = Field(default=None, ge=1950, le=2100, strict=True)


def empty_setup():
    return {'version': 0, 'automobile_enabled': False, 'locations': [], 'vehicle_added': [],
            'vehicle_hidden_makes': [], 'vehicle_hidden_models': []}


def load_row(m, company_id, session):
    return session.scalar(select(m.Record).where(m.Record.company_id == company_id, m.Record.kind == KIND))


def load(m, company_id, session):
    row = load_row(m, company_id, session)
    return {**empty_setup(), **(row.data if row else {})}


def vehicle_options(setup):
    """Default catalogue minus what the shop hid, plus what it added. Models are sorted for pickers."""
    hidden_makes = {key(name) for name in setup['vehicle_hidden_makes']}
    hidden_models = {(key(item['make']), key(item['model'])) for item in setup['vehicle_hidden_models']}
    added = {key(entry['make']): entry for entry in setup['vehicle_added']}
    result, used = [], set()
    for entry in CATALOG:
        name_key = key(entry['make'])
        extra = added.get(name_key)
        used.add(name_key)
        if name_key in hidden_makes and not extra:
            continue
        models = [{'name': name, 'custom': False} for name in entry['models'] if (name_key, key(name)) not in hidden_models]
        seen = {key(item['name']) for item in models}
        models += [{'name': name, 'custom': True} for name in (extra or {}).get('models', []) if key(name) not in seen]
        if name_key in hidden_makes and not models:
            continue
        result.append({'make': entry['make'], 'type': entry['type'], 'custom': False, 'models': sorted(models, key=lambda item: item['name'].casefold())})
    for name_key, entry in added.items():
        if name_key in used:
            continue
        models = [{'name': name, 'custom': True} for name in entry.get('models', [])]
        result.append({'make': entry['make'], 'type': entry.get('type', 'car'), 'custom': True, 'models': sorted(models, key=lambda item: item['name'].casefold())})
    order = list(VEHICLE_TYPES)
    result.sort(key=lambda item: (order.index(item['type']), item['make'].casefold()))
    return result


def view(setup):
    return {**setup, 'vehicle_options': vehicle_options(setup), 'default_catalog': CATALOG, 'vehicle_types': VEHICLE_TYPES,
            'catalog_version': CATALOG_VERSION, 'location_limit_per_item': LOCATION_ITEM_LIMIT}


def location_usage(m, company_id, session):
    counts = {}
    for item in session.scalars(select(m.Record).where(m.Record.company_id == company_id, m.Record.kind == 'item')):
        for location_id in (item.data or {}).get('location_ids') or []:
            counts[location_id] = counts.get(location_id, 0) + 1
    return counts


def build_setup(m, company_id, body, current, session):
    seen_names, locations = set(), []
    existing = {row['id']: row for row in current['locations']}
    submitted_ids = {row.id for row in body.locations if row.id}
    unknown = submitted_ids - set(existing)
    if unknown:
        raise HTTPException(422, 'A location in this request does not exist. Reload Settings and try again')
    for row in body.locations:
        name = tidy(row.name)
        if not name:
            raise HTTPException(422, 'Enter a name for every location')
        if key(name) in seen_names:
            raise HTTPException(422, f'Location "{name}" is listed twice')
        seen_names.add(key(name))
        locations.append({'id': row.id or 'loc-' + uuid4().hex[:12], 'name': name, 'active': row.active})
    removed = [row for location_id, row in existing.items() if location_id not in submitted_ids]
    if removed:
        usage = location_usage(m, company_id, session)
        for row in removed:
            if usage.get(row['id']):
                raise HTTPException(409, f'"{row["name"]}" is used by {usage[row["id"]]} item(s). Archive it instead of removing it')
    added, seen_makes = [], set()
    for entry in body.vehicle_added:
        make = tidy(entry.make)
        if key(make) in seen_makes:
            raise HTTPException(422, f'Make "{make}" is listed twice')
        seen_makes.add(key(make))
        models, seen_models = [], set()
        for name in entry.models:
            name = tidy(name)
            if not name or len(name) > 60:
                raise HTTPException(422, 'Model names must be 1 to 60 characters')
            if key(name) not in seen_models:
                seen_models.add(key(name)); models.append(name)
        added.append({'make': make, 'type': entry.type, 'models': models})
    hidden_makes = sorted({tidy(name) for name in body.vehicle_hidden_makes if tidy(name)}, key=str.casefold)
    hidden_models, seen_pairs = [], set()
    for item in body.vehicle_hidden_models:
        pair = (key(item.make), key(item.model))
        if pair not in seen_pairs:
            seen_pairs.add(pair); hidden_models.append({'make': tidy(item.make), 'model': tidy(item.model)})
    return {'automobile_enabled': body.automobile_enabled, 'locations': locations, 'vehicle_added': added,
            'vehicle_hidden_makes': hidden_makes, 'vehicle_hidden_models': hidden_models}


def clean_item_extras(m, company_id, kind, values, previous, session):
    """Validate and normalise the optional item fields a request actually sent. Returns what to store."""
    if not values:
        return {}
    previous = previous or {}
    if kind != 'item':
        if any(values.get(name) for name in EXTRA_KEYS):
            raise HTTPException(422, 'Locations and vehicle details belong to items')
        return {}
    setup = load(m, company_id, session)
    result = {}
    if 'location_ids' in values:
        ids = list(dict.fromkeys(values['location_ids'] or []))
        if len(ids) > LOCATION_ITEM_LIMIT:
            raise HTTPException(422, f'Choose at most {LOCATION_ITEM_LIMIT} locations for one item')
        known = {row['id']: row for row in setup['locations']}
        before = set(previous.get('location_ids') or [])
        for location_id in ids:
            if location_id not in known:
                raise HTTPException(422, 'Choose locations from the list set up in Settings')
            if not known[location_id]['active'] and location_id not in before:
                raise HTTPException(422, f'Location "{known[location_id]["name"]}" is archived')
        result['location_ids'] = ids
    sent = {name: values[name] for name in AUTOMOBILE_KEYS if name in values}
    if sent:
        if 'part_grade' in sent and sent['part_grade'] not in PART_GRADES:
            raise HTTPException(422, 'Choose OEM, aftermarket, used or refurbished')
        fitment = []
        for row in sent.get('vehicle_fitment') or []:
            row = dict(row)
            make, model = tidy(row.get('make')), tidy(row.get('model'))
            if not make:
                raise HTTPException(422, 'Every vehicle fitment needs a make')
            year_from, year_to = row.get('year_from'), row.get('year_to')
            if year_from is not None and year_to is not None and year_from > year_to:
                raise HTTPException(422, f'Fitment years for {make} {model} run backwards')
            fitment.append({'make': make, 'model': model, 'year_from': year_from, 'year_to': year_to})
        if 'vehicle_fitment' in sent:
            if len(fitment) > 60:
                raise HTTPException(422, 'List at most 60 vehicle fitments on one item')
            sent['vehicle_fitment'] = fitment
        for name in ('oem_number', 'part_brand'):
            if name in sent:
                sent[name] = tidy(sent[name])
        changed = {name: value for name, value in sent.items() if value != previous.get(name, [] if name == 'vehicle_fitment' else '')}
        if changed and not setup['automobile_enabled']:
            raise HTTPException(422, 'Turn on the Automobile module in Settings before adding vehicle details to items')
        result.update(sent)
    return result


def export_columns(m, company_id, session):
    """Extra item-list columns: where an item is kept, plus vehicle details when the Automobile module is on."""
    setup = load(m, company_id, session)
    names = {row['id']: row['name'] for row in setup['locations']}
    headers = ['Location']
    if setup['automobile_enabled']:
        headers += ['OEM number', 'Brand', 'Part grade', 'Fits vehicles']

    def fits(row):
        parts = []
        for item in row.data.get('vehicle_fitment') or []:
            years = ''
            if item.get('year_from') or item.get('year_to'):
                years = f" {item.get('year_from') or ''}-{item.get('year_to') or ''}"
            parts.append(tidy(f"{item.get('make', '')} {item.get('model', '')}") + years)
        return '; '.join(parts)

    def cells(row):
        values = [', '.join(names.get(location_id, '') for location_id in row.data.get('location_ids') or [] if names.get(location_id))]
        if setup['automobile_enabled']:
            values += [row.data.get('oem_number', ''), row.data.get('part_brand', ''), row.data.get('part_grade', ''), fits(row)]
        return values
    return headers, cells


def validate_backup(groups):
    """Restore guard: a backed-up setup must still be well formed before it is trusted."""
    rows = [row for row in groups['records'] if row['kind'] == KIND]
    if len(rows) > 1:
        raise ValueError('More than one inventory setup in backup')
    ids = set()
    for row in rows:
        data = row['data']
        if not isinstance(data.get('automobile_enabled', False), bool) or not isinstance(data.get('version', 0), int):
            raise ValueError('Invalid inventory setup')
        for location in data.get('locations', []):
            if (not isinstance(location, dict) or not isinstance(location.get('id'), str) or not location['id']
                    or not isinstance(location.get('name'), str) or not 0 < len(location['name']) <= 40
                    or not isinstance(location.get('active'), bool) or location['id'] in ids):
                raise ValueError('Invalid item location in backup')
            ids.add(location['id'])
    for row in groups['records']:
        if row['kind'] != 'item':
            continue
        extra = row['data'].get('location_ids')
        if extra is not None and (not isinstance(extra, list) or len(extra) > LOCATION_ITEM_LIMIT
                                  or any(not isinstance(i, str) or i not in ids for i in extra)):
            raise ValueError('Item points at an unknown location')
        fits = row['data'].get('vehicle_fitment')
        if fits is not None and (not isinstance(fits, list) or len(fits) > 60 or any(
                not isinstance(f, dict) or not isinstance(f.get('make'), str) or not f['make'] for f in fits)):
            raise ValueError('Invalid vehicle fitment in backup')


def install(app, m):
    base = '/api/companies/{company_id}/inventory-setup'

    @app.get(base)
    def get_setup(company_id: str, user=Depends(m.current_user), session: Session = Depends(m.db)):
        m.company_for(company_id, user, session)
        return view(load(m, company_id, session))

    @app.put(base)
    def put_setup(company_id: str, body: SetupIn, user=Depends(m.current_user), session: Session = Depends(m.db)):
        company = m.lock_company(company_id, user, session)
        if company.owner_id != user.id:
            raise HTTPException(403, 'Only the owner can change item locations and business modules')
        row = load_row(m, company_id, session)
        current = {**empty_setup(), **(row.data if row else {})}
        if body.version != current['version']:
            raise HTTPException(409, 'Setup changed on another device. Reload it and apply your change again')
        saved = {**build_setup(m, company_id, body, current, session), 'version': current['version'] + 1}
        if row:
            row.data = saved
        else:
            session.add(m.Record(company_id=company_id, kind=KIND, name='Inventory setup', date=DateType.today(), amount=0, data=saved))
        m.audit(session, company_id, user, 'inventory_setup.updated', 'company', company_id, {
            'automobile_enabled': saved['automobile_enabled'], 'locations': len(saved['locations']),
            'vehicle_added': len(saved['vehicle_added'])})
        session.commit()
        return view(saved)
