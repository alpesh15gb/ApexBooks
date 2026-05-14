# Core models kept for backward compatibility.
# Full accounting models live in app.models.accounting.
from sqlalchemy import String, Numeric, Boolean, JSON, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin


class Company(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'companies'
    company_name: Mapped[str] = mapped_column(String(255))
    gstin: Mapped[str] = mapped_column(String(15), unique=True)
    pan: Mapped[str | None] = mapped_column(String(10))
    state_code: Mapped[str] = mapped_column(String(2))
    address: Mapped[dict] = mapped_column(JSON)
    business_type: Mapped[str] = mapped_column(String(50))
    registration_type: Mapped[str] = mapped_column(String(50))
    e_invoice_applicable: Mapped[bool] = mapped_column(Boolean, default=False)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    company_id: Mapped[str] = mapped_column(String(36))

# NOTE: Party, Item, SalesInvoice were REMOVED from here because they
# conflict with PartyModel, ItemModel, InvoiceModel in app.models.accounting.
# All accounting models now live exclusively in app.models.accounting.