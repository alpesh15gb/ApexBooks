from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
from app.utils.validators import validate_gstin, validate_pan, VALID_STATE_CODES

class Address(BaseModel):
    type: str | None = None
    line1: str
    line2: str | None = None
    city: str
    pincode: str
    state_code: str
    state_name: str | None = None
    country: str = 'India'
    @field_validator('state_code')
    @classmethod
    def state_valid(cls, v):
        if v not in VALID_STATE_CODES: raise ValueError('Invalid Indian state code')
        return v
class Contact(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    designation: str | None = None
    is_primary: bool = False
class BankAccount(BaseModel):
    bank_name: str
    account_no: str
    ifsc: str | None = None
    account_type: str | None = None
class Money(BaseModel):
    amount: Decimal = Field(decimal_places=2)
