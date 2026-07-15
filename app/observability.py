import contextvars
import json
import logging
from datetime import datetime, timezone

from app.config import log_json, log_level


request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for name in ("method", "path", "status_code", "duration_ms", "client_ip"):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    level = getattr(logging, log_level(), logging.INFO)
    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    if log_json():
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
        ))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger("uvicorn.access").disabled = True
