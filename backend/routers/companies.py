import base64
import io
import re
from accounting import (
    NUMBERED_KINDS, audit, audit_changes, company_for, company_obj, current_user, db, lock_company,
)
from datetime import date as DateType
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from gst_identifiers import require_gstin
from models import (
    AuditEvent, BankAccount, Company, CompanyMember, CompanyPreference, CompanyTaxProfile,
    NumberSeries, Record, User,
)
from pydantic import BaseModel, Field
from schemas import CompanyInput, CompanyPreferenceInput, CompanyUpdate, MemberInput, SeriesInput
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


router = APIRouter()


@router.get('/api/companies')
def companies(user: User = Depends(current_user), session: Session = Depends(db)):
    member_companies = select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)
    return [company_obj(c, session, user) for c in session.scalars(select(Company).where(or_(Company.owner_id == user.id, Company.id.in_(member_companies))).order_by(Company.name))]


@router.post('/api/companies')
def create_company(body: CompanyInput, user: User = Depends(current_user), session: Session = Depends(db)):
    if body.tax_mode not in {'regular', 'composition', 'unregistered'}: raise HTTPException(422, 'Unsupported tax profile')
    body.gstin = require_gstin(body.gstin, 'Company GSTIN')
    if body.tax_mode == 'unregistered' and body.gstin: raise HTTPException(422, 'An unregistered company cannot have a GSTIN')
    if body.tax_mode in {'regular','composition'} and not body.gstin:raise HTTPException(422,'A GST registered company needs its GSTIN')
    if body.state_code and not re.fullmatch(r'\d{2}', body.state_code): raise HTTPException(422, 'State code must contain two digits')
    if body.gstin and body.state_code != body.gstin[:2]: raise HTTPException(422, 'GSTIN and state code must match')
    if body.tax_mode in {'regular', 'composition'} and not body.state_code: raise HTTPException(422, 'State code is required for GST registered companies')
    values = body.model_dump(exclude={'tax_mode'}); values['gstin'] = body.gstin.strip().upper(); values['book_label']=body.book_label.strip()
    c = Company(owner_id=user.id, **values); session.add(c); session.flush(); session.add(CompanyTaxProfile(company_id=c.id, mode=body.tax_mode)); session.add(CompanyPreference(company_id=c.id,document_template='modern')); audit(session, c.id, user, 'company.created', 'company', c.id, {'tax_mode': body.tax_mode}); session.commit(); session.refresh(c); return company_obj(c, session)


@router.patch('/api/companies/{company_id}')
def update_company(company_id: str, body: CompanyUpdate, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can update company details')
    profile = session.get(CompanyTaxProfile, company_id)
    mode = profile.mode if profile else 'regular'
    gstin = body.gstin.strip().upper()
    state = body.state_code.strip()
    if not body.name.strip(): raise HTTPException(422, 'Company name is required')
    gstin = require_gstin(gstin, 'Company GSTIN', unchanged=company.gstin if state == company.state_code else None)
    if state and not re.fullmatch(r'\d{2}', state): raise HTTPException(422, 'State code must contain two digits')
    if gstin and gstin[:2] != state: raise HTTPException(422, 'GSTIN and state code must match')
    if mode in {'regular', 'composition'} and not state: raise HTTPException(422, 'State code is required for GST registered companies')
    if mode in {'regular', 'composition'} and not gstin: raise HTTPException(422, 'A GST registered company needs its GSTIN')
    if mode == 'unregistered' and gstin: raise HTTPException(422, 'An unregistered company cannot have a GSTIN')
    tracked_fields = ('name', 'gstin', 'state_code', 'address', 'book_label')
    before = {key: getattr(company, key) for key in tracked_fields}
    company.name = body.name.strip(); company.gstin = gstin; company.state_code = state; company.address = body.address.strip()
    if 'book_label' in body.model_fields_set:company.book_label=body.book_label.strip()
    audit(session, company_id, user, 'company.updated', 'company', company_id,
          audit_changes(before, {key: getattr(company, key) for key in tracked_fields}))
    session.commit()
    return company_obj(company, session, user)


@router.get('/api/companies/{company_id}/preferences')
def get_preferences(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    preference = session.get(CompanyPreference, company_id)
    return {'document_template': preference.document_template if preference else 'classic'}


class DocumentBranding(BaseModel):
    phone: str = Field(default='', max_length=32)
    email: str = Field(default='', max_length=254)
    bank_name: str = Field(default='', max_length=120)
    account_number: str = Field(default='', max_length=64)
    ifsc: str = Field(default='', max_length=20)
    branch: str = Field(default='', max_length=120)
    upi_id: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=1500)
    terms: str = Field(default='', max_length=3000)
    logo: str = Field(default='', max_length=350000)
    signature: str = Field(default='', max_length=350000)


def branding_for(company_id, session):
    row = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'document_branding'))
    return row.data if row else {}


BANK_FIELDS = ('bank_name', 'account_number', 'ifsc', 'branch')


def with_payment_details(company_id, snapshot, current, session):
    """Bank/UPI details for a customer document. A document saved with bank details keeps them as issued;
    one saved before any were entered uses today's branding, then the company's own bank account."""
    result = dict(snapshot)
    if not any(result.get(key) for key in BANK_FIELDS):
        if any(current.get(key) for key in BANK_FIELDS):
            result.update({key: current.get(key, '') for key in BANK_FIELDS})
        else:
            bank = session.scalar(select(BankAccount).where(BankAccount.company_id == company_id).order_by(BankAccount.name))
            if bank: result.update(bank_name=bank.name, account_number=bank.account_hint, ifsc='', branch='')
    for key in ('upi_id', 'phone', 'email', 'signature', 'notes', 'terms'):
        if not result.get(key) and current.get(key): result[key] = current[key]
    return result


@router.get('/api/companies/{company_id}/document-branding')
def get_branding(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    return branding_for(company_id, session)


@router.put('/api/companies/{company_id}/document-branding')
def set_branding(company_id: str, body: DocumentBranding, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can change document branding')
    # An omitted asset is not a request to delete it. In particular, saving bank
    # details from another client must not silently clear the company logo.
    existing_branding = branding_for(company_id, session)
    supplied_branding = body.model_dump(exclude_unset=True)
    body = DocumentBranding.model_validate({**existing_branding, **supplied_branding})
    saved_branding = body.model_dump()
    for asset in ('logo', 'signature'):
        if asset not in existing_branding and asset not in supplied_branding:
            saved_branding.pop(asset, None)
    from PIL import Image as PillowImage
    for value in (body.logo, body.signature):
        if not value: continue
        try:
            match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)', value)
            if not match: raise ValueError()
            raw = base64.b64decode(match.group(2), validate=True)
            if len(raw) > 250000: raise ValueError()
            with PillowImage.open(io.BytesIO(raw)) as image:
                if image.format not in {'PNG', 'JPEG'} or image.width * image.height > 4_000_000: raise ValueError()
                image.verify()
        except Exception: raise HTTPException(422, 'Logo and signature must be valid PNG/JPEG images under 250 KB and 4 megapixels')
    row = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'document_branding'))
    if row: row.data = saved_branding
    else: session.add(Record(company_id=company_id, kind='document_branding', name='Document branding', date=DateType.today(), amount=Decimal('0'), data=saved_branding))
    audit(session, company_id, user, 'document_branding.updated', 'company', company_id)
    session.commit()
    return saved_branding


@router.patch('/api/companies/{company_id}/document-branding')
def patch_branding(company_id: str, body: DocumentBranding, user: User = Depends(current_user), session: Session = Depends(db)):
    return set_branding(company_id, body, user, session)


@router.put('/api/companies/{company_id}/preferences')
def set_preferences(company_id: str, body: CompanyPreferenceInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can change company preferences')
    if body.document_template not in {'classic', 'modern', 'compact', 'bold', 'minimal', 'elegant', 'vintage', 'mrp_discount', 'evergreen'}:
        raise HTTPException(422, 'Unsupported document layout')
    preference = session.get(CompanyPreference, company_id)
    if preference: preference.document_template = body.document_template
    else: session.add(CompanyPreference(company_id=company_id, document_template=body.document_template))
    audit(session, company_id, user, 'preferences.updated', 'company', company_id, {'document_template': body.document_template})
    session.commit()
    return {'document_template': body.document_template}


@router.get('/api/companies/{company_id}/audit-events')
def audit_events(company_id: str, limit: int = Query(default=50, ge=1, le=200), user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can view the activity log')
    rows = session.scalars(select(AuditEvent).where(AuditEvent.company_id == company_id).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit))
    return [{'id': row.id, 'occurred_at': row.occurred_at.isoformat(), 'actor': session.get(User, row.actor_id).email,
             'action': row.action, 'entity_type': row.entity_type, 'entity_id': row.entity_id, 'details': row.details} for row in rows]


@router.get('/api/companies/{company_id}/members')
def list_members(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    rows = [(session.get(User, company.owner_id).email, 'owner')]
    rows += [(session.get(User, m.user_id).email, m.role) for m in session.scalars(select(CompanyMember).where(CompanyMember.company_id == company_id))]
    return [{'email': email, 'role': role} for email, role in rows]


@router.post('/api/companies/{company_id}/members', status_code=201)
def add_member(company_id: str, body: MemberInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can manage members')
    if body.role not in {'editor', 'viewer'}: raise HTTPException(422, 'Role must be editor or viewer')
    invitee = session.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not invitee: raise HTTPException(404, 'User must register before being added')
    if invitee.id == user.id: raise HTTPException(409, 'Owner already has access')
    member = CompanyMember(company_id=company_id, user_id=invitee.id, role=body.role)
    session.add(member)
    audit(session, company_id, user, 'member.added', 'user', invitee.id, {'role': body.role})
    try: session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'User already has access')
    return {'email': invitee.email, 'role': member.role}


@router.delete('/api/companies/{company_id}/members/{member_email}')
def remove_member(company_id: str, member_email: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can manage members')
    invitee = session.scalar(select(User).where(User.email == member_email.strip().lower()))
    member = session.scalar(select(CompanyMember).where(CompanyMember.company_id == company_id, CompanyMember.user_id == invitee.id)) if invitee else None
    if not member: raise HTTPException(404, 'Member not found')
    session.delete(member); audit(session, company_id, user, 'member.removed', 'user', invitee.id); session.commit()
    return {'removed': True}


@router.get('/api/companies/{company_id}/number-series')
def list_number_series(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    rows = session.scalars(select(NumberSeries).where(NumberSeries.company_id == company_id).order_by(NumberSeries.financial_year.desc(), NumberSeries.kind))
    return [{'kind': r.kind, 'financial_year': r.financial_year, 'prefix': r.prefix, 'next_number': r.next_number} for r in rows]


@router.put('/api/companies/{company_id}/number-series')
def set_number_series(company_id: str, body: SeriesInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can change numbering')
    if body.kind not in NUMBERED_KINDS: raise HTTPException(422, 'Unsupported document type')
    if len(body.prefix) > 5:
        raise HTTPException(422, 'Use a prefix of up to 5 characters to fit the document number')
    row = session.scalar(select(NumberSeries).where(NumberSeries.company_id == company_id, NumberSeries.kind == body.kind, NumberSeries.financial_year == body.financial_year))
    if row and body.kind in ('pos', 'credit_note') and row.next_number >= 10 ** (9 - len(body.prefix)):
        raise HTTPException(422, 'Use a shorter prefix to fit the remaining sequence')
    if row: row.prefix = body.prefix
    else:
        row = NumberSeries(company_id=company_id, kind=body.kind, financial_year=body.financial_year, prefix=body.prefix, next_number=1)
        session.add(row)
    audit(session, company_id, user, 'number_series.updated', 'company', company_id, {'kind': body.kind, 'financial_year': body.financial_year, 'prefix': body.prefix})
    session.commit()
    return {'kind': row.kind, 'financial_year': row.financial_year, 'prefix': row.prefix, 'next_number': row.next_number}
