"""Centralized logging configuration with sensitive data redaction.

Provides a structured logging setup that replaces raw ``print()`` calls
across ingestion scripts and utilities.  The redaction filter ensures that
database connection strings, absolute file paths, raw SQL identifiers, and
system credentials never reach stdout/stderr or container logs.
"""

from __future__ import annotations

import logging
import re

# ---------------------------------------------------------------------------
# Redaction patterns
# ---------------------------------------------------------------------------

# Matches connection strings that embed credentials (mssql, postgres, mysql, etc.)
_CONN_STR_RE = re.compile(
    r"(?i)(driver|server|host|uid|user|pwd|password|database|db)"
    r"=[^;\"\']+(?:;|$)",
)

# Matches URL-format connection strings with embedded credentials
# pragma: allowlist secret
_URL_CRED_RE = re.compile(
    r"(?i)[a-z][a-z0-9+\-.]*://[^:@/\s]+:[^@/\s]+@",
)

# Matches absolute file paths that could reveal internal directory layout
_ABS_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?:/(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]+)"
    r"(?![A-Za-z0-9_./-])",
)

# Matches raw SQL identifiers that leak table/column structures
_SQL_IDENT_RE = re.compile(
    r"(?i)(?:SELECT|FROM|JOIN|WHERE|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)"
    r"[^\n]{0,200}",
)

# Matches credential-like values (API keys, tokens, secrets)
_CREDENTIAL_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|pwd|credential)"
    r"[:=]\s*[\"']?([A-Za-z0-9_\-./+]{8,})",
)


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts sensitive metadata from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        record.msg = redacted
        record.args = ()
        return True

    @staticmethod
    def redact(text: str) -> str:
        """Return *text* with sensitive information replaced by ``[REDACTED]``."""
        text = _CREDENTIAL_RE.sub(r"\1=[REDACTED]", text)
        text = _URL_CRED_RE.sub("[REDACTED]", text)
        text = _CONN_STR_RE.sub("[REDACTED]", text)
        text = _SQL_IDENT_RE.sub("[SQL_REDACTED]", text)
        # Only redact absolute paths that are not part of a URL or already-redacted
        text = _ABS_PATH_RE.sub("[PATH_REDACTED]", text)
        return text


class StructuredFormatter(logging.Formatter):
    """Formatter that outputs structured, timestamped log lines."""

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        return (
            f"{record.asctime} | {record.levelname:8s} | "
            f"{record.name:30s} | {record.message}"
        )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def setup_logging(level: int | str = logging.INFO) -> None:
    """Configure the root logger with a redacting console handler.

    Safe to call multiple times: subsequent calls only adjust the level.
    """
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    handler.addFilter(SensitiveDataFilter())

    # Avoid double-registering handlers
    if not any(
        isinstance(h, logging.StreamHandler)
        and h.formatter is not None
        and isinstance(h.formatter, StructuredFormatter)
        for h in root.handlers
    ):
        root.addHandler(handler)

    if isinstance(level, str):
        level = logging.getLevelName(level.upper())
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger, ensuring root is configured."""
    if not logging.getLogger().handlers:
        setup_logging()
    return logging.getLogger(name)


def sanitize_exception(exc: BaseException) -> str:
    """Return a redacted string representation of *exc*.

    Database connection strings, credentials, and absolute paths embedded in
    exception messages are replaced with ``[REDACTED]`` before they reach
    log output.
    """
    return SensitiveDataFilter.redact(str(exc))
