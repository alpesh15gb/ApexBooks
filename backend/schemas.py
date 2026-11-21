import base64
import io
import re
from business_calendar import business_today
from datetime import date as DateType
from decimal import Decimal
from fastapi import HTTPException
from inventory_setup import FitmentIn
from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class BookLabelInput(BaseModel):
    book_label: str = Field(default='', max_length=80)
    @field_validator('book_label',mode='before')
    @classmethod
    def trim_book_label(cls,value):
        return value.strip() if isinstance(value,str) else value


class CompanyInput(BookLabelInput):
    name: str = Field(min_length=1, max_length=120)
    gstin: str = ''
    state_code: str = ''
    address: str = ''
    tax_mode: str = 'regular'


class CompanyPreferenceInput(BaseModel):
    document_template: str


class CompanyUpdate(BookLabelInput):
    name: str = Field(min_length=1, max_length=120)
    gstin: str = Field(default='', max_length=15)
    state_code: str = Field(default='', max_length=2)
    address: str = Field(default='', max_length=500)


class RecordInput(BaseModel):
    kind: str
    name: str = ''
    number: str = ''
    date: DateType = Field(default_factory=business_today)
    amount: Decimal = Field(default=Decimal('0'), max_digits=15, decimal_places=2, allow_inf_nan=False)
    data: dict = Field(default_factory=dict)


class AccountInput(BaseModel):
    code: str = Field(min_length=1, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=120)
    category: str


class BankAccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    account_hint: str = Field(default='', max_length=32)


class JournalLineInput(BaseModel):
    account_id: str
    debit: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    credit: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)


class JournalInput(BaseModel):
    date: DateType
    reference: str = Field(min_length=1, max_length=80)
    memo: str = Field(default='', max_length=500)
    lines: list[JournalLineInput] = Field(min_length=2, max_length=100)


class ReversalInput(BaseModel):
    date: DateType
    reference: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)


class LockInput(BaseModel):
    locked_through: DateType


class StatementInputLine(BaseModel):
    date: DateType
    description: str = Field(min_length=1, max_length=500)
    reference: str = Field(default='', max_length=120)
    amount: Decimal = Field(max_digits=15, decimal_places=2, allow_inf_nan=False)


class StatementImport(BaseModel):
    dry_run: bool = False
    bank_account_id: str = 'default'
    lines: list[StatementInputLine] = Field(min_length=1, max_length=5000)


class MatchInput(BaseModel):
    record_id: str


class BankMatchAllocationInput(BaseModel):
    record_id: str
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)


class ReconciliationReviewInput(BaseModel):
    bank_account_id: str = 'default'
    as_of: DateType
    opening_balance: Decimal = Field(default=Decimal('0'), max_digits=15, decimal_places=2, allow_inf_nan=False)
    note: str = Field(default='', max_length=500)


class MemberInput(BaseModel):
    email: str
    role: str


class SeriesInput(BaseModel):
    kind: str
    financial_year: int = Field(ge=2000, le=2100)
    prefix: str = Field(min_length=1, max_length=6, pattern=r'^[A-Z0-9-]+$')


class OcrInput(BaseModel):
    image_data_url: str = Field(min_length=50, max_length=7_000_000)


class MasterRow(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gstin: str = Field(default='', max_length=15)
    address: str = Field(default='', max_length=500)
    phone: str = Field(default='', max_length=32)
    email: str = Field(default='', max_length=254)
    party_type: str = Field(default='both', max_length=16)
    hsn: str = Field(default='', max_length=16)
    unit: str = Field(default='', max_length=24)
    sale_rate: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2)
    purchase_rate: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2)
    gst_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100, max_digits=5, decimal_places=2)
    image_data_url:str=Field(default='',max_length=90000)
    image_thumbnail:str=Field(default='',max_length=22000)
    barcode: str = Field(default='',max_length=80)
    item_type: str = Field(default='goods',pattern=r'^(goods|services)$')
    tax_treatment: str = Field(default='taxable',pattern=r'^(taxable|nil_rated|exempt|non_gst)$')
    track_stock: bool = False
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    payment_terms_days: int | None = Field(default=None, ge=0, le=3650, strict=True)
    credit_limit: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    is_active: bool = Field(default=True, strict=True)
    shipping_address: str = Field(default='', max_length=500)
    # Optional item details. Older clients omit them and their existing values are kept.
    location_ids: list[str] = Field(default_factory=list, max_length=5)
    vehicle_fitment: list[FitmentIn] = Field(default_factory=list, max_length=60)
    oem_number: str = Field(default='', max_length=40)
    part_brand: str = Field(default='', max_length=40)
    part_grade: str = Field(default='', max_length=12)


def validate_master_defaults(master, kind, *, previous=None):
    if kind == 'item' and master.track_stock and master.item_type == 'services' and not (previous and previous.get('track_stock') and previous.get('item_type') == 'services'):
        raise HTTPException(422, 'Stock tracking is supported for goods only; create services without stock tracking')
    if master.credit_limit is not None and kind != 'party':
        raise HTTPException(422, 'Credit limit belongs to a party')
    if master.shipping_address and kind != 'party':
        raise HTTPException(422, 'Shipping address belongs to a party')
    if master.low_stock_threshold is not None and (kind != 'item' or not master.track_stock or master.item_type != 'goods'):
        raise HTTPException(422, 'Low-stock thresholds require a stock-tracked goods item')
    if master.payment_terms_days is not None and kind != 'party':
        raise HTTPException(422, 'Payment terms belong to a party')


def validate_item_image(master):
    from PIL import Image as PillowImage
    for value in (master.image_data_url,master.image_thumbnail):
        if not value:continue
        try:
            match=re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)',value)
            if not match:raise ValueError()
            raw=base64.b64decode(match.group(2),validate=True)
            if len(raw)>67500:raise ValueError()
            with PillowImage.open(io.BytesIO(raw)) as image:
                expected = {'png':'PNG','jpeg':'JPEG'}[match.group(1)]
                if image.format != expected or image.width*image.height>1_000_000 or getattr(image,'n_frames',1)!=1:raise ValueError()
                image.verify()
            # verify() checks structure but JPEG scan truncation can survive it.
            # Decode only after the byte, format and pixel bounds have passed.
            with PillowImage.open(io.BytesIO(raw)) as image:
                image.load()
        except Exception:raise HTTPException(422,'Use a valid static PNG or JPEG below 67 KB and one megapixel')


class MasterImport(BaseModel):
    kind: str
    dry_run: bool = True
    rows: list[MasterRow] = Field(min_length=1, max_length=500)


class OpeningStockInput(BaseModel):
    item_id: str
    date: DateType
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    unit_cost: Decimal = Field(gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)


class StockAdjustmentInput(BaseModel):
    item_id: str
    date: DateType
    direction: str
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    unit_cost: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=500)


class StockCountInput(BaseModel):
    item_id: str
    date: DateType
    counted_quantity: Decimal = Field(ge=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    stock_snapshot: str = Field(pattern=r'^[0-9a-f]{64}$')
    unit_cost: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=500)
