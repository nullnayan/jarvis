"""Central logging setup for the Jarvis backend."""

import logging
import os
import re
from datetime import date
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs")
LOG_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-5s | %(message)s"


class SecretRedactionFilter(logging.Filter):
    """Redact credential values and credential-bearing URLs before any handler sees them."""
    def filter(self, record):
        message = record.getMessage()
        for key, value in os.environ.items():
            if len(value) >= 8 and re.search(r"(?i)(?:api_?key|auth_?token|access_?token|secret|password)", key):
                message = message.replace(value, "[REDACTED]")
        message = re.sub(r"\b(?:gsk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,}|nvapi-[A-Za-z0-9_-]{20,}|\d{8,12}:[A-Za-z0-9_-]{30,})", "[REDACTED]", message)
        message = re.sub(r"(?i)([?&](?:token|api_key|key|access_token)=)[^&\s]+", r"\1[REDACTED]", message)
        message = re.sub(r"(?i)(Bearer\s+)\S+", r"\1[REDACTED]", message)
        record.msg, record.args = message, ()
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    logger.addFilter(SecretRedactionFilter())

    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    filename = os.path.join(LOG_DIR, f"jarvis-{date.today().isoformat()}.log")
    file_handler = RotatingFileHandler(
        filename, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger
