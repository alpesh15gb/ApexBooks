import time
from decimal import Decimal
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.database import create_all_for_dev
from app.core.exceptions import APIError, api_error_handler
from app.core.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.core.tenant_context import get_current_tenant, get_context
from app.core.tenant_middleware import TenantMiddleware
from app.services.audit_service import AuditLog

settings = get_settings()
app = FastAPI(title=settings.app_name, version='0.2.0', openapi_version='3.1.0')

# Tenant isolation (must run before auth)
app.add_middleware(TenantMiddleware)

# CORS - restricted to configured origins
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True,
                   allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'], allow_headers=['*'])

# Security middleware (production only)
if settings.environment == 'production':
    app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Exception handlers
app.add_exception_handler(APIError, api_error_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request data",
                "details": exc.errors()
            }
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": {"code": "HTTP_ERROR", "message": exc.detail}}
    )


@app.middleware('http')
async def add_request_metadata(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers['X-Process-Time-ms'] = str(round((time.time() - start) * 1000, 2))
    response.headers['X-API-Version'] = 'v1'
    response.headers['X-Tenant-ID'] = get_context().get('tenant_id', 'unknown')
    return response


@app.on_event('startup')
def startup():
    if settings.environment in {'development', 'test'}:
        create_all_for_dev()


app.include_router(router)


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'service': settings.app_name,
        'version': '0.2.0',
        'environment': settings.environment,
        'tenant_context': get_context().get('tenant_id')
    }


@app.post('/tenants/validate')
def validate_tenant():
    """Validate current tenant context is set."""
    tid = get_current_tenant()
    return {'tenant_id': tid, 'valid': True}