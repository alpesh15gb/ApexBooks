from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator
from app.schemas.common import Address, Contact, BankAccount
from app.utils.validators import validate_gstin, validate_pan

class CompanyCreate(BaseModel):
    company_name: str; gstin: str; pan: str | None = None; state_code: str
    address: Address; business_type: str; registration_type: str = 'Regular'
    fiscal_year_start: str = 'April'; e_invoice_applicable: bool = False; e_way_bill_applicable: bool = False
    @field_validator('gstin')
    @classmethod
    def gstin_valid(cls, v): return validate_gstin(v)
    @field_validator('pan')
    @classmethod
    def pan_valid(cls, v): return validate_pan(v)
class Company(CompanyCreate):
    company_id: UUID = Field(default_factory=uuid4); created_at: datetime = Field(default_factory=datetime.utcnow); updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserRegister(BaseModel):
    email: str; password: str; full_name: str; company: CompanyCreate
class Login(BaseModel): email: str; password: str
class Token(BaseModel): access_token: str; refresh_token: str; token_type: str = 'bearer'

class Party(BaseModel):
    party_id: UUID = Field(default_factory=uuid4); party_type: str; party_name: str; gstin: str | None = None; pan: str | None = None
    party_category: str = 'B2B'; registration_type: str = 'Regular'; addresses: list[Address] = []; contacts: list[Contact] = []
    bank_accounts: list[BankAccount] = []; credit_limit: Decimal = Decimal('0.00'); credit_days: int = 0; currency: str = 'INR'
    tds_applicable: bool = False; tds_section: str | None = None; opening_balance: Decimal = Decimal('0.00'); opening_balance_date: date | None = None
    tags: list[str] = []; custom_fields: dict = {}
    @field_validator('gstin')
    @classmethod
    def gstin_valid(cls, v): return validate_gstin(v)

class Item(BaseModel):
    item_id: UUID = Field(default_factory=uuid4); item_code: str; item_name: str; item_type: str
    hsn_code: str | None = None; sac_code: str | None = None; description: str | None = None; unit_of_measure: str = 'Nos'
    gst_rate: Decimal = Decimal('18'); cess_rate: Decimal = Decimal('0'); is_nil_rated: bool = False; is_exempt: bool = False; is_non_gst: bool = False
    selling_price: Decimal = Decimal('0'); purchase_price: Decimal = Decimal('0'); stock_keeping_unit: bool = False; custom_fields: dict = {}

class InvoiceLineInput(BaseModel):
    item_id: UUID | None = None; item_code: str; item_name: str; hsn_code: str | None = None; sac_code: str | None = None
    quantity: Decimal; unit: str = 'Nos'; unit_price: Decimal; discount_percent: Decimal = Decimal('0'); discount_amount: Decimal = Decimal('0')
    gst_rate: Decimal = Decimal('18'); cess_rate: Decimal = Decimal('0')
class InvoiceCreate(BaseModel):
    invoice_type: str = 'Regular'; invoice_date: date; due_date: date | None = None; supply_type: str = 'B2B'
    customer_id: UUID | None = None; supplier_id: UUID | None = None; billing_address: Address; shipping_address: Address | None = None
    place_of_supply: str; reverse_charge: bool = False; line_items: list[InvoiceLineInput]; notes: str | None = None
class Payment(BaseModel):
    payment_id: UUID = Field(default_factory=uuid4); payment_type: str; payment_mode: str; payment_date: date; party_id: UUID; amount: Decimal
    currency: str = 'INR'; reference_no: str | None = None; narration: str | None = None; tds_amount: Decimal = Decimal('0'); allocations: list[dict] = []; status: str = 'Draft'
