from sqlalchemy import String, Numeric, Boolean, JSON, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin

class Company(UUIDMixin, TimestampMixin, Base):
    __tablename__='companies'
    company_name: Mapped[str] = mapped_column(String(255)); gstin: Mapped[str] = mapped_column(String(15), unique=True)
    pan: Mapped[str | None] = mapped_column(String(10)); state_code: Mapped[str] = mapped_column(String(2)); address: Mapped[dict] = mapped_column(JSON)
    business_type: Mapped[str] = mapped_column(String(50)); registration_type: Mapped[str] = mapped_column(String(50)); e_invoice_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
class User(UUIDMixin, TimestampMixin, Base):
    __tablename__='users'
    email: Mapped[str] = mapped_column(String(255), unique=True); password_hash: Mapped[str] = mapped_column(String(255)); full_name: Mapped[str] = mapped_column(String(255)); company_id: Mapped[str] = mapped_column(String(36))
class Party(UUIDMixin, TimestampMixin, Base):
    __tablename__='parties'
    party_type: Mapped[str] = mapped_column(String(20)); party_name: Mapped[str] = mapped_column(String(255)); gstin: Mapped[str | None] = mapped_column(String(15)); custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
class Item(UUIDMixin, TimestampMixin, Base):
    __tablename__='items'
    item_code: Mapped[str] = mapped_column(String(64)); item_name: Mapped[str] = mapped_column(String(255)); item_type: Mapped[str] = mapped_column(String(20)); gst_rate: Mapped[float] = mapped_column(Numeric(5,2))
class SalesInvoice(UUIDMixin, TimestampMixin, Base):
    __tablename__='sales_invoices'
    invoice_number: Mapped[str] = mapped_column(String(64)); invoice_date: Mapped[Date] = mapped_column(Date); customer_id: Mapped[str | None] = mapped_column(String(36)); grand_total: Mapped[float] = mapped_column(Numeric(14,2)); status: Mapped[str] = mapped_column(String(30))
