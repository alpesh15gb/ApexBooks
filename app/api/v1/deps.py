from fastapi import Header
from app.core.tenant_context import get_current_tenant


def current_tenant(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID")) -> str:
    """FastAPI dependency: returns tenant_id from contextvar (set by TenantMiddleware)."""
    return get_current_tenant()


def current_user() -> str | None:
    """FastAPI dependency: returns current user_id from contextvar."""
    from app.core.tenant_context import get_current_user
    return get_current_user()