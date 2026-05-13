from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import time
import json
import logging
from app.core.security import decode_token
from app.core.exceptions import APIError

logger = logging.getLogger('gst_api')

TENANT_CONTEXT = {'current_tenant_id': None, 'current_user_id': None}

def get_current_tenant() -> str:
    tid = TENANT_CONTEXT.get('current_tenant_id')
    if not tid:
        raise APIError('NO_TENANT', 'Tenant context not set', status_code=500)
    return tid

def get_current_user() -> str:
    uid = TENANT_CONTEXT.get('current_user_id')
    if not uid:
        raise APIError('NO_USER', 'User context not set', status_code=500)
    return uid

class TenantMiddleware:
    """Extracts tenant_id from JWT or X-Tenant-ID header and sets context."""
    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            request = Request(scope, receive)

            # Try JWT first
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                try:
                    payload = decode_token(token)
                    TENANT_CONTEXT['current_tenant_id'] = payload.get('tenant_id')
                    TENANT_CONTEXT['current_user_id'] = payload.get('sub', payload.get('user_id'))
                except Exception:
                    pass

            # Fallback to header
            if not TENANT_CONTEXT['current_tenant_id']:
                tenant_id = request.headers.get('X-Tenant-ID')
                if tenant_id:
                    TENANT_CONTEXT['current_tenant_id'] = tenant_id

            # Validate tenant is set for API routes
            if scope['path'].startswith('/api/') and not TENANT_CONTEXT['current_tenant_id']:
                response = JSONResponse(
                    status_code=401,
                    content={'success': False, 'error': 'TENANT_REQUIRED', 'message': 'Tenant ID required for API access'}
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

    def __init__(self, app):
        self.app = app

class StructuredLoggingMiddleware:
    """Emits structured JSON logs for every request."""
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        request = Request(scope, receive)
        path = request.url.path

        # Skip noisy health/docs endpoints
        if path in ('/health', '/docs', '/openapi.json', '/redoc'):
            await self.app(scope, receive, send)
            return

        response_start = time.time()

        # Capture response
        response_body = b''
        response_started = False

        async def wrapped_send(message):
            nonlocal response_body, response_started
            if message['type'] == 'http.response.start':
                response_started = True
                status = message['status']
            elif message['type'] == 'http.response.body':
                response_body += message.get('body', b'')
                if status >= 400 and len(response_body) > 500:
                    response_body = response_body[:500]

            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(json.dumps({
                "level": "ERROR",
                "event": "request_error",
                "method": request.method,
                "path": path,
                "duration_ms": duration_ms,
                "error": str(e),
                "tenant_id": TENANT_CONTEXT.get('current_tenant_id'),
                "user_id": TENANT_CONTEXT.get('current_user_id'),
            }))
            raise

        duration_ms = round((time.time() - start_time) * 1000, 2)
        log_entry = {
            "level": "INFO",
            "event": "request",
            "method": request.method,
            "path": path,
            "status": getattr(logging, '_status', 200),
            "duration_ms": duration_ms,
            "tenant_id": TENANT_CONTEXT.get('current_tenant_id'),
            "user_id": TENANT_CONTEXT.get('current_user_id'),
            "client_ip": request.client.host if request.client else None,
        }

        if duration_ms > 500:
            log_entry['level'] = 'WARN'
            log_entry['event'] = 'slow_request'

        logger.info(json.dumps(log_entry))