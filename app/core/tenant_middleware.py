from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import time
import json
import logging
from app.core.security import decode_token
from app.core.exceptions import APIError
from app.core.tenant_context import set_tenant_context, clear_tenant_context, get_current_tenant

logger = logging.getLogger('gst_api')


class TenantMiddleware:
    """Extracts tenant_id from JWT or X-Tenant-ID header and sets contextvar."""

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            request = Request(scope, receive)

            tenant_id = None
            user_id = None

            # Try JWT first
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                try:
                    payload = decode_token(token)
                    tenant_id = payload.get('tenant_id')
                    user_id = payload.get('sub', payload.get('user_id'))
                except Exception:
                    pass

            # Fallback to header
            if not tenant_id:
                tenant_id = request.headers.get('X-Tenant-ID')

            # Validate tenant is set for API routes (excluding auth)
            is_auth = '/auth/' in scope['path']
            if scope['path'].startswith('/api/') and not tenant_id and not is_auth:
                response = JSONResponse(
                    status_code=401,
                    content={'success': False, 'error': 'TENANT_REQUIRED',
                             'message': 'Tenant ID required for API access'}
                )
                await response(scope, receive, send)
                return

            set_tenant_context(tenant_id=tenant_id, user_id=user_id)

        try:
            await self.app(scope, receive, send)
        finally:
            if scope['type'] == 'http':
                clear_tenant_context()

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
            from app.core.tenant_context import get_context
            ctx = get_context()
            logger.error(json.dumps({
                "level": "ERROR",
                "event": "request_error",
                "method": request.method,
                "path": path,
                "duration_ms": duration_ms,
                "error": str(e),
                "tenant_id": ctx.get('tenant_id'),
                "user_id": ctx.get('user_id'),
            }))
            raise

        duration_ms = round((time.time() - start_time) * 1000, 2)
        from app.core.tenant_context import get_context
        ctx = get_context()
        log_entry = {
            "level": "INFO",
            "event": "request",
            "method": request.method,
            "path": path,
            "status": getattr(logging, '_status', 200),
            "duration_ms": duration_ms,
            "tenant_id": ctx.get('tenant_id'),
            "user_id": ctx.get('user_id'),
            "client_ip": request.client.host if request.client else None,
        }

        if duration_ms > 500:
            log_entry['level'] = 'WARN'
            log_entry['event'] = 'slow_request'

        logger.info(json.dumps(log_entry))