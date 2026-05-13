from collections.abc import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import get_settings
from app.models.base import Base

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def create_all_for_dev() -> None:
    Base.metadata.create_all(bind=engine)

def schema_name(company_id: str) -> str:
    return 'tenant_' + ''.join(ch if ch.isalnum() else '_' for ch in company_id.lower())[:48]

def ensure_tenant_schema(db: Session, company_id: str) -> str:
    """PostgreSQL schema-per-tenant hook. SQLite/dev falls back to shared tables with tenant_id."""
    name = schema_name(company_id)
    if engine.dialect.name == 'postgresql':
        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS {name}'))
    return name
