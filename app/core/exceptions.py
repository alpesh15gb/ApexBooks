from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any

class APIError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None, details: Any = None, status_code: int = 400):
        self.code, self.message, self.field, self.details, self.status_code = code, message, field, details, status_code

class APIResponse(BaseModel):
    success: bool = True
    data: Any = None
    meta: dict[str, Any] | None = None
    message: str | None = None

def ok(data: Any = None, message: str | None = None, meta: dict[str, Any] | None = None):
    return {"success": True, "data": data, "meta": meta, "message": message}

async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": {"code": exc.code, "message": exc.message, "field": exc.field, "details": exc.details}})
