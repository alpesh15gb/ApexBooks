"""
Tenant context using contextvars for thread-safe, async-safe storage.

Replaces the previous module-level dict which leaked state between requests
in multi-worker/multi-threaded deployments (Gunicorn/Uvicorn).
"""
import contextvars

_tenant_context: contextvars.ContextVar[dict] = contextvars.ContextVar(
    'tenant_context', default={}
)


def set_tenant_context(tenant_id: str | None = None, user_id: str | None = None):
    """Set tenant context for the current request/thread."""
    _tenant_context.set({'tenant_id': tenant_id, 'user_id': user_id})


def clear_tenant_context():
    """Clear tenant context (called at end of request)."""
    _tenant_context.set({})


def get_current_tenant() -> str:
    """Return the current tenant_id from contextvar."""
    ctx = _tenant_context.get()
    tid = ctx.get('tenant_id')
    if not tid:
        from app.core.exceptions import APIError
        raise APIError('NO_TENANT', 'Tenant context not set', status_code=500)
    return tid


def get_current_user() -> str | None:
    """Return the current user_id from contextvar."""
    ctx = _tenant_context.get()
    return ctx.get('user_id')


def get_context() -> dict:
    """Return a copy of the current tenant context."""
    return dict(_tenant_context.get())