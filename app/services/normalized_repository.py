from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, text
from sqlalchemy.orm import Session, selectinload
from app.core.exceptions import APIError
from app.models.accounting import (
    PartyModel, ItemModel, InvoiceModel, InvoiceLineModel,
    PaymentModel, GLEntryModel, GSTReturnModel
)
from app.models.e2e import NumberingSeriesRecord
from app.services.gst_engine import calculate_tax, classify_gstr1

MONEY_FIELDS = [
    'subtotal', 'total_discount', 'total_cgst', 'total_sgst',
    'total_igst', 'total_cess', 'round_off', 'grand_total',
    'amount_paid', 'outstanding_amount'
]


def d(value, default=None):
    if value in (None, ''):
        return default
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return default


def dec(value):
    return Decimal(str(value or 0))


def model_dict(obj, extra: dict | None = None):
    data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    if extra:
        data.update(extra)
    return jsonable_encoder(data)


class NormalizedAccountingRepository:

    def next_number(self, db: Session, tenant_id: str, series_key: str, prefix: str, padding: int = 3) -> str:
        rec = db.query(NumberingSeriesRecord).filter_by(
            tenant_id=tenant_id, series_key=series_key
        ).with_for_update().first()
        if not rec:
            rec = NumberingSeriesRecord(
                tenant_id=tenant_id, series_key=series_key,
                prefix=prefix, current=0, padding=padding
            )
            db.add(rec)
            db.flush()
        rec.current += 1
        db.flush()
        return f'{rec.prefix}{rec.current:0{rec.padding}d}'

    # ---- Parties ----
    def create_party(self, db: Session, tenant_id: str, payload: dict) -> dict:
        p = jsonable_encoder(payload)
        p.setdefault('party_id', str(uuid4()))
        addresses = p.get('addresses') or []
        state_code = p.get('state_code') or (
            addresses[0].get('state_code') if addresses else None
        )
        rec = PartyModel(
            tenant_id=tenant_id,
            party_id=p['party_id'],
            party_type=p.get('party_type', 'Customer'),
            party_name=p['party_name'],
            gstin=p.get('gstin'),
            pan=p.get('pan'),
            party_category=p.get('party_category'),
            registration_type=p.get('registration_type'),
            state_code=state_code,
            credit_limit=dec(p.get('credit_limit')),
            credit_days=int(p.get('credit_days') or 0),
            opening_balance=dec(p.get('opening_balance')),
            tds_applicable=bool(p.get('tds_applicable', False)),
            addresses=addresses,
            contacts=p.get('contacts') or [],
            bank_accounts=p.get('bank_accounts') or [],
            custom_fields=p.get('custom_fields') or {},
        )
        db.add(rec)
        db.flush()
        return model_dict(rec)

    def list_parties(self, db: Session, tenant_id: str, search: str | None = None, party_type: str | None = None) -> list[dict]:
        q = db.query(PartyModel).filter_by(tenant_id=tenant_id, is_deleted=False)
        if search:
            q = q.filter(PartyModel.party_name.ilike(f'%{search}%'))
        if party_type:
            q = q.filter(PartyModel.party_type == party_type)
        return [model_dict(r) for r in q.order_by(PartyModel.party_name).all()]

    def get_party(self, db: Session, tenant_id: str, party_id: str) -> PartyModel:
        rec = db.query(PartyModel).filter_by(
            tenant_id=tenant_id, party_id=party_id, is_deleted=False
        ).first()
        if not rec:
            raise APIError('PARTY_NOT_FOUND', 'Party not found', status_code=404)
        return rec

    def update_party(self, db: Session, tenant_id: str, party_id: str, payload: dict) -> dict:
        rec = self.get_party(db, tenant_id, party_id)
        for k, v in jsonable_encoder(payload).items():
            if hasattr(rec, k) and k not in {'id', 'tenant_id', 'party_id'}:
                setattr(rec, k, v)
        db.flush()
        return model_dict(rec)

    # ---- Items ----
    def create_item(self, db: Session, tenant_id: str, payload: dict) -> dict:
        p = jsonable_encoder(payload)
        p.setdefault('item_id', str(uuid4()))
        rec = ItemModel(
            tenant_id=tenant_id,
            item_id=p['item_id'],
            item_code=p['item_code'],
            item_name=p['item_name'],
            item_type=p.get('item_type', 'Product'),
            hsn_code=p.get('hsn_code'),
            sac_code=p.get('sac_code'),
            unit_of_measure=p.get('unit_of_measure', 'Nos'),
            gst_rate=dec(p.get('gst_rate')),
            cess_rate=dec(p.get('cess_rate')),
            selling_price=dec(p.get('selling_price')),
            purchase_price=dec(p.get('purchase_price')),
            stock_keeping_unit=bool(p.get('stock_keeping_unit', False)),
            custom_fields=p.get('custom_fields') or {},
        )
        db.add(rec)
        db.flush()
        return model_dict(rec)

    def list_items(self, db: Session, tenant_id: str, search: str | None = None) -> list[dict]:
        q = db.query(ItemModel).filter_by(tenant_id=tenant_id, is_deleted=False)
        if search:
            q = q.filter(ItemModel.item_name.ilike(f'%{search}%'))
        return [model_dict(r) for r in q.order_by(ItemModel.item_code).all()]

    def get_item(self, db: Session, tenant_id: str, item_id: str) -> ItemModel:
        rec = db.query(ItemModel).filter_by(
            tenant_id=tenant_id, item_id=item_id, is_deleted=False
        ).first()
        if not rec:
            raise APIError('ITEM_NOT_FOUND', 'Item not found', status_code=404)
        return rec

    def update_item(self, db: Session, tenant_id: str, item_id: str, payload: dict) -> dict:
        rec = self.get_item(db, tenant_id, item_id)
        for k, v in jsonable_encoder(payload).items():
            if hasattr(rec, k) and k not in {'id', 'tenant_id', 'item_id'}:
                setattr(rec, k, v)
        db.flush()
        return model_dict(rec)

    # ---- Invoices ----
    def create_invoice(self, db: Session, tenant_id: str, kind: str, payload: dict) -> dict:
        p = jsonable_encoder(payload)
        invoice_id = p.get('invoice_id') or str(uuid4())
        prefix = 'PINV-' if kind == 'purchase' else 'INV-'
        invoice_number = p.get('invoice_number') or self.next_number(
            db, tenant_id, f'{kind}_invoice', prefix
        )
        invoice_date = d(p.get('invoice_date'), date.today()) or date.today()
        party_id = p.get('customer_id') or p.get('supplier_id') or p.get('party_id')
        party_gstin = p.get('party_gstin') or p.get('buyer_gstin')
        if party_id and not party_gstin:
            party = db.query(PartyModel).filter_by(
                tenant_id=tenant_id, party_id=party_id, is_deleted=False
            ).first()
            if party:
                party_gstin = party.gstin
        calc = calculate_tax(
            p.get('seller_state_code', '27'),
            p.get('place_of_supply', '27'),
            p.get('supply_type', 'B2B'),
            p.get('line_items', []),
            p.get('reverse_charge', False),
            p.get('composition_scheme', False),
        )
        rec = InvoiceModel(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            invoice_kind=kind,
            invoice_number=invoice_number,
            invoice_type=p.get('invoice_type', 'Regular'),
            invoice_date=invoice_date,
            due_date=d(p.get('due_date')),
            party_id=party_id,
            party_gstin=party_gstin,
            place_of_supply=p.get('place_of_supply', '27'),
            supply_type=p.get('supply_type', 'B2B'),
            reverse_charge=bool(p.get('reverse_charge', False)),
            status='Draft',
            payment_status='Unpaid',
            billing_address=p.get('billing_address') or {},
            shipping_address=p.get('shipping_address') or {},
            notes=p.get('notes'),
            custom_fields=p.get('custom_fields') or {},
            **{f: dec(calc.get(f)) for f in MONEY_FIELDS if f in calc}
        )
        rec.outstanding_amount = rec.grand_total
        db.add(rec)
        db.flush()
        for idx, line in enumerate(calc['line_items'], start=1):
            db.add(InvoiceLineModel(
                tenant_id=tenant_id,
                invoice_pk=rec.id,
                line_no=idx,
                item_id=line.get('item_id'),
                item_code=line.get('item_code'),
                item_name=line.get('item_name') or line.get('description') or 'Item',
                hsn_code=line.get('hsn_code'),
                sac_code=line.get('sac_code'),
                quantity=dec(line.get('quantity')),
                unit=line.get('unit', 'Nos'),
                unit_price=dec(line.get('unit_price')),
                discount_amount=dec(line.get('discount_amount')),
                taxable_value=dec(line.get('taxable_value')),
                gst_rate=dec(line.get('gst_rate')),
                cgst_amount=dec(line.get('cgst_amount')),
                sgst_amount=dec(line.get('sgst_amount')),
                igst_amount=dec(line.get('igst_amount')),
                cess_amount=dec(line.get('cess_amount')),
                total_amount=dec(line.get('total_amount')),
            ))
        db.flush()
        return self.invoice_dict(rec)

    def invoice_dict(self, rec: InvoiceModel) -> dict:
        return model_dict(rec, {'line_items': [model_dict(l) for l in rec.lines]})

    def list_invoices(self, db: Session, tenant_id: str, kind: str, status: str | None = None) -> list[dict]:
        q = db.query(InvoiceModel).options(
            selectinload(InvoiceModel.lines)
        ).filter_by(tenant_id=tenant_id, invoice_kind=kind)
        if status:
            q = q.filter(InvoiceModel.status == status)
        return [self.invoice_dict(r) for r in q.order_by(
            InvoiceModel.invoice_date.desc(), InvoiceModel.id.desc()
        ).all()]

    def get_invoice(self, db: Session, tenant_id: str, kind: str, invoice_id: str) -> InvoiceModel:
        rec = db.query(InvoiceModel).options(
            selectinload(InvoiceModel.lines)
        ).filter_by(
            tenant_id=tenant_id, invoice_kind=kind, invoice_id=invoice_id
        ).first()
        if not rec:
            raise APIError('INVOICE_NOT_FOUND', 'Invoice not found', status_code=404)
        return rec

    def submit_invoice(self, db: Session, tenant_id: str, kind: str, invoice_id: str) -> dict:
        from sqlalchemy import exc
        rec = self.get_invoice(db, tenant_id, kind, invoice_id)
        if rec.status != 'Draft':
            return self.invoice_dict(rec)

        rec.status = 'Submitted'
        tax_total = dec(rec.total_cgst) + dec(rec.total_sgst) + dec(rec.total_igst) + dec(rec.total_cess)

        if kind == 'sales':
            entries = [
                ('Accounts Receivable', rec.grand_total, 0),
                ('Sales', 0, rec.subtotal),
                ('GST Payable', 0, tax_total),
            ]
        else:
            # Purchase: debit expense and input tax credit, credit supplier
            entries = [
                ('Purchases', rec.subtotal, 0),
                ('Input GST Credit', tax_total, 0),
                ('Accounts Payable', 0, rec.grand_total),
            ]

        try:
            for account, debit, credit in entries:
                db.add(GLEntryModel(
                    tenant_id=tenant_id,
                    posting_date=rec.invoice_date,
                    account=account,
                    party_id=rec.party_id,
                    voucher_type=f'{kind}_invoice',
                    voucher_id=invoice_id,
                    debit=dec(debit),
                    credit=dec(credit),
                ))
            db.flush()

            # Verify balance BEFORE committing
            total_debit = sum(entry[1] for entry in entries)
            total_credit = sum(entry[2] for entry in entries)
            if abs(total_debit - total_credit) > Decimal('0.01'):
                raise ValueError(
                    f'GL imbalance: debit={total_debit}, credit={total_credit}'
                )
            db.commit()
        except Exception:
            db.rollback()
            rec.status = 'Draft'
            raise

        db.refresh(rec)
        return self.invoice_dict(rec)

    # ---- Payments ----
    def create_payment(self, db: Session, tenant_id: str, payload: dict) -> dict:
        p = jsonable_encoder(payload)
        p.setdefault('payment_id', str(uuid4()))
        amount = dec(p.get('amount'))
        tds = dec(p.get('tds_amount'))
        rec = PaymentModel(
            tenant_id=tenant_id,
            payment_id=p['payment_id'],
            payment_type=p.get('payment_type', 'Receive'),
            payment_mode=p.get('payment_mode'),
            payment_date=d(p.get('payment_date'), date.today()) or date.today(),
            party_id=p.get('party_id'),
            amount=amount,
            tds_amount=tds,
            net_amount=amount - tds,
            reference_no=p.get('reference_no'),
            narration=p.get('narration'),
            allocations=p.get('allocations') or [],
            status=p.get('status', 'Submitted'),
        )
        db.add(rec)
        db.flush()
        return model_dict(rec)

    def list_payments(self, db: Session, tenant_id: str) -> list[dict]:
        return [model_dict(r) for r in db.query(PaymentModel).filter_by(
            tenant_id=tenant_id
        ).order_by(PaymentModel.payment_date.desc()).all()]

    # ---- Reports / GST ----
    def gl_entries(self, db: Session, tenant_id: str, party_id: str | None = None) -> list[dict]:
        q = db.query(GLEntryModel).filter_by(tenant_id=tenant_id)
        if party_id:
            q = q.filter(GLEntryModel.party_id == party_id)
        return [model_dict(r) for r in q.order_by(
            GLEntryModel.posting_date, GLEntryModel.id
        ).all()]

    def gstr1_summary(self, db: Session, tenant_id: str, month: int, year: int) -> dict:
        q = db.query(InvoiceModel).filter(
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'sales',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        )
        invoices = q.all()
        buckets = {
            k: {'count': 0, 'taxable': Decimal('0'), 'tax': Decimal('0'), 'total': Decimal('0')}
            for k in ['B2B', 'B2CL', 'B2CS', 'EXP', 'CDNR', 'CDNUR']
        }
        for inv in invoices:
            if inv.invoice_date.month != month or inv.invoice_date.year != year:
                continue
            cls = classify_gstr1({
                'gstin': inv.party_gstin,
                'supply_type': inv.supply_type,
                'seller_state_code': '27',
                'place_of_supply': inv.place_of_supply,
                'grand_total': inv.grand_total,
            })
            b = buckets[cls]
            b['count'] += 1
            b['taxable'] += dec(inv.subtotal)
            b['tax'] += dec(inv.total_cgst) + dec(inv.total_sgst) + dec(inv.total_igst) + dec(inv.total_cess)
            b['total'] += dec(inv.grand_total)
        return jsonable_encoder({'month': month, 'year': year, 'tables': buckets})

    def gstr3b(self, db: Session, tenant_id: str, month: int, year: int) -> dict:
        sales = db.query(InvoiceModel).filter_by(
            tenant_id=tenant_id, invoice_kind='sales', status='Submitted'
        ).all()
        purchases = db.query(InvoiceModel).filter_by(
            tenant_id=tenant_id, invoice_kind='purchase', status='Submitted'
        ).all()

        def filt(rows):
            return [r for r in rows if r.invoice_date.month == month and r.invoice_date.year == year]

        sales = filt(sales)
        purchases = filt(purchases)
        return jsonable_encoder({
            'sup_details': {
                'txval': sum(dec(r.subtotal) for r in sales),
                'iamt': sum(dec(r.total_igst) for r in sales),
                'camt': sum(dec(r.total_cgst) for r in sales),
                'samt': sum(dec(r.total_sgst) for r in sales),
                'csamt': sum(dec(r.total_cess) for r in sales),
            },
            'itc_elg': {
                'iamt': sum(dec(r.total_igst) for r in purchases),
                'camt': sum(dec(r.total_cgst) for r in purchases),
                'samt': sum(dec(r.total_sgst) for r in purchases),
                'csamt': sum(dec(r.total_cess) for r in purchases),
            },
        })


normalized_repo = NormalizedAccountingRepository()