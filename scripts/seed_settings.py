#!/usr/bin/env python3
"""
Seed Script: Generates default settings for a new tenant during onboarding.
Run: python scripts/seed_settings.py --tenant-id <id> --email <admin@email>
"""
import sys
import os
import argparse
import uuid
from datetime import datetime, date
from decimal import Decimal

sys.path.insert(0, '//Vault/ApexBooks/gst-api-engine')
os.chdir('//Vault/ApexBooks/gst-api-engine')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, SessionLocal
from app.core.config import get_settings
from app.core.security import hash_password, create_access_token, create_refresh_token
from app.services.settings_service import settings_service, _default_settings
from app.models.e2e import CompanyRecord, UserRecord, ApiKeyRecord
from app.models.accounting import (
    PartyModel, ItemModel, InvoiceModel, InvoiceLineModel,
    PaymentModel, GLEntryModel, GSTReturnModel,
)


def seed_tenant(db, tenant_id: str, business_name: str, email: str, password: str):
    """Complete onboarding seed for a new tenant company."""

    # 1. Create Company Record
    company = CompanyRecord(
        company_id=tenant_id,
        company_name=business_name,
        gstin='',  # To be filled during setup
        pan='',
        state_code='',
        payload=_default_settings(),
        schema_name='tenant_' + tenant_id.replace('-', '_'),
    )
    db.add(company)
    db.flush()
    print(f'  ✓ Company record created: {company.company_id}')

    # 2. Create Admin User
    user = UserRecord(
        user_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        email=email,
        full_name='Administrator',
        password_hash=hash_password(password),
        roles=['admin'],
        permissions=['*'],
        is_active=True,
    )
    db.add(user)
    db.flush()
    print(f'  ✓ Admin user created: {email}')

    # 3. Generate API Key
    raw_key = 'gst_' + uuid.uuid4().hex + uuid.uuid4().hex
    api_key = ApiKeyRecord(
        key_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name='Default Integration Key',
        key_hash=hash_password(raw_key),
        is_active=True,
    )
    db.add(api_key)
    db.flush()
    print(f'  ✓ API key generated: {api_key.key_id}')
    print(f'    ⚠ Store this key now — it will not be shown again:')
    print(f'    {raw_key}')

    # 4. Verify settings loaded
    settings = settings_service.get_settings(db, tenant_id)
    assert settings is not None
    assert settings['business']['business_name'] == ''
    assert settings['gst']['core']['enabled'] == True
    print(f'  ✓ Default settings loaded ({len(settings)} categories)')

    # 5. Generate tokens
    access = create_access_token(user)
    refresh = create_refresh_token(user)
    print(f'  ✓ Auth tokens generated (access: {len(access)} chars)')

    db.commit()
    return {
        'company_id': company.company_id,
        'user_id': user.user_id,
        'api_key_id': api_key.key_id,
        'api_key': raw_key,
        'access_token': access,
        'refresh_token': refresh,
        'settings': settings,
    }


def main():
    parser = argparse.ArgumentParser(description='Seed a new tenant for onboarding')
    parser.add_argument('--tenant-id', default=str(uuid.uuid4()), help='Tenant/Company ID')
    parser.add_argument('--email', default='admin@example.com', help='Admin email')
    parser.add_argument('--password', default='Admin@123456', help='Admin password')
    parser.add_argument('--db', default='sqlite:///./dev.db', help='Database URL')
    args = parser.parse_args()

    print(f'\n{"="*60}')
    print(f'  GST API Engine — Tenant Seed')
    print(f'{"="*60}')
    print(f'  Tenant ID:  {args.tenant_id}')
    print(f'  Email:      {args.email}')
    print(f'  Database:   {args.db}')
    print(f'{"="*60}\n')

    engine = create_engine(args.db)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        result = seed_tenant(db, args.tenant_id, 'New Company', args.email, args.password)
        print(f'\n{"="*60}')
        print(f'  SEEDING COMPLETE')
        print(f'{"="*60}')
        print(f'  Company ID:    {result["company_id"]}')
        print(f'  User ID:       {result["user_id"]}')
        print(f'  API Key ID:    {result["api_key_id"]}')
        print(f'  Settings:      {len(result["settings"])} categories')
        print(f'{"="*60}\n')
    except Exception as e:
        db.rollback()
        print(f'  ✗ ERROR: {e}')
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()