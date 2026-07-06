import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from backend.app.core.logging import request_id_ctx_var

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that captures or generates a unique request_id for tracing.
    It binds the ID to the context-local logger variable and sets it on the outgoing response.
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Set the request ID for the duration of this async task chain
        token = request_id_ctx_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            # Clean up token context to prevent memory/context leak across requests
            request_id_ctx_var.reset(token)
            
        response.headers["X-Request-ID"] = request_id
        return response
