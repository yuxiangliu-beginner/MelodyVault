"""Rotating logs; never log credential objects or HTTP bodies."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re

_SECRET = re.compile(
    r'(?i)([\"\']?(?:access_token|refresh_token|id_token|client_secret|api_key|'
    r'authorization|password)[\"\']?\s*[:=]\s*)(?:\"[^\"]*\"|\'[^\']*\'|[^\s&,;}]+)'
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")

class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = _BEARER.sub("Bearer [REDACTED]", super().format(record))
        return _SECRET.sub(r"\1[REDACTED]", rendered)


def configure_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("melodyvault")
    logger.setLevel(level)
    logger.propagate = False
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    handler = RotatingFileHandler(log_dir / "melodyvault.log", maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    return logger


def close_logging() -> None:
    logger = logging.getLogger("melodyvault")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
