# SPDX-License-Identifier: MIT
"""D2 logging implementation (F15): stdlib only, domain-free, digest-safe.

- One root logger ``academic_core``; module loggers for application /
  infrastructure / adapters / ui. NEVER in ``domain/``.
- Structured record fields: timestamp, level, event_code, component,
  operation, message (+ optional correlation_id, exception_type).
- Correlation ids are runtime-only (UUID), never embedded in domain
  values, digests, provenance, or compare() inputs.
- Redaction: home paths trimmed, secret-looking values replaced.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re

ROOT_NAME = "academic_core"

_correlation: contextvars.ContextVar[str] = contextvars.ContextVar(
    "acore_correlation_id", default="")

_SECRET_RE = re.compile(r"(?i)(password|passwd|token|api[_-]?key|secret|bearer|oauth|credential)")
_HOME = os.path.expanduser("~")


def set_correlation_id(value: str) -> None:
    _correlation.set(value or "")


def get_correlation_id() -> str:
    return _correlation.get()


def new_correlation_id() -> str:
    import uuid
    cid = uuid.uuid4().hex[:12]
    set_correlation_id(cid)
    return cid


def redact(text: str) -> str:
    """Trim home paths and mask secret-looking ``key=value`` pairs."""
    if not isinstance(text, str):
        text = str(text)
    if _HOME and _HOME not in ("~", "") and _HOME in text:
        text = text.replace(_HOME, "<home>")
    parts = re.split(r"(\s+)", text)
    out = []
    for p in parts:
        if "=" in p and _SECRET_RE.search(p.split("=", 1)[0]):
            out.append(p.split("=", 1)[0] + "=***")
        else:
            out.append(p)
    text = "".join(out)
    if len(text) > 1024:
        text = text[:1021] + "..."
    return text


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        record.event_code = getattr(record, "event_code", "AC-OK-000")
        record.component = getattr(record, "component", record.name)
        record.operation = getattr(record, "operation", "-")
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        return True


def get_logger(component: str) -> logging.Logger:
    """Module logger under the ``academic_core`` root (never for domain)."""
    if component == "academic_core.domain" or component.startswith("academic_core.domain."):
        raise ValueError("domain must not log (D2-I003)")
    logger = logging.getLogger(component)
    if not any(isinstance(f, _ContextFilter) for f in logger.filters):
        logger.addFilter(_ContextFilter())
    return logger


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger(ROOT_NAME)
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(event_code)s %(component)s %(operation)s "
            "[cid=%(correlation_id)s] %(message)s"))
        handler.addFilter(_ContextFilter())
        root.addHandler(handler)
    return root


def log_event(logger: logging.Logger, level: int, event_code: str,
              component: str, operation: str, message: str) -> None:
    logger.log(level, redact(message),
               extra={"event_code": event_code, "component": component,
                      "operation": operation})
