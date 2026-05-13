from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.rate_limit import check_rate_limit

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ['/health', '/docs', '/openapi.json', '/redoc']:
            return await call_next(request)
        client_ip = request.client.host if request.client else 'unknown'
        key = f"{client_ip}:{request.url.path}"
        allowed, remaining = check_rate_limit(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={'error': 'RATE_LIMIT_EXCEEDED', 'message': 'Too many requests. Please try again later.'}
            )
        response: Response = await call_next(request)
        response.headers['X-RateLimit-Limit'] = str(remaining + 1)
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response