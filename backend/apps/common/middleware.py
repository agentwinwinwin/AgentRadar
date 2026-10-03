import logging
import time
import uuid

logger = logging.getLogger("agentradar.request")


class RequestContextMiddleware:
    """Attach a safe correlation ID and emit one structured request summary."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID", "")
        try:
            request_id = str(uuid.UUID(request_id))
        except (ValueError, AttributeError):
            request_id = str(uuid.uuid4())

        request.request_id = request_id
        started = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "user_id": getattr(getattr(request, "user", None), "pk", None),
            },
        )
        return response
