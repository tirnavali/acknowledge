import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record (JSONL format)."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("event", "duration_ms", "event_id", "media_id", "person_id", "face_id"):
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val
        if record.exc_info:
            obj["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            obj["traceback"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


def setup_logging(log_dir: Path) -> None:
    """Configure root logger: structured JSON to file + human-readable WARNING+ to console."""
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "acknowledge.jsonl",
        maxBytes=10 * 1024 * 1024,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JsonFormatter())

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))

    root.addHandler(file_handler)
    root.addHandler(console_handler)
