"""OpenTelemetry trace context middleware."""

from __future__ import annotations

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class TracingMiddleware(BaseHTTPMiddleware):
    """Inject W3C Trace Context into structlog and response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Extract trace context from incoming headers and propagate."""
        # Extract W3C traceparent header if present
        traceparent: str | None = request.headers.get("traceparent")
        trace_id: str = ""
        span_id: str = ""

        if traceparent:
            parts = traceparent.split("-")
            if len(parts) >= 3:
                trace_id = parts[1]
                span_id = parts[2]

        # TODO: Initialize OTel span from extracted context
        # For now, bind trace IDs to structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id or "none",
            span_id=span_id or "none",
            http_method=request.method,
            http_path=request.url.path,
        )

        logger.info("request_start")

        response: Response = await call_next(request)

        # Propagate trace context in response headers
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id

        logger.info("request_end", http_status=response.status_code)

        return response
