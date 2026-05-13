from fastapi import Header

def current_tenant(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID")) -> str:
    return x_tenant_id or "public"
