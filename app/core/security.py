"""Security + privacy hardening: strict CSP, security headers, loopback guard,
and a log filter that forbids rsIDs/genotypes from ever being logged.
"""
from __future__ import annotations

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .. import config

# Strict CSP. `connect-src 'self'` means the SPA cannot fetch/XHR/WebSocket to any
# third-party host, which blocks the usual background-exfiltration channels for a
# compromised dependency. It is a strong mitigation, not an absolute guarantee
# (e.g. top-level navigation is not fully constrained). Everything is same-origin
# and self-hosted — no CDN, no web fonts, no third-party requests at all.
CSP = (
    "default-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), usb=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


def assert_loopback(host: str) -> None:
    """Refuse to run on a non-loopback interface (never expose off-device)."""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError(
            f"Refusing to bind {host!r}: this app must run on loopback only "
            f"(127.0.0.1). Binding a public interface would risk exposing user data."
        )


_SENSITIVE = re.compile(r"\b(rs\d{2,})\b|\b([ACGT]{2})\b", re.IGNORECASE)


class NoGenotypeLogFilter(logging.Filter):
    """Belt-and-suspenders: redact anything that looks like an rsID or genotype
    from log records so user genetic content can never leak into logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            if _SENSITIVE.search(msg):
                record.msg = _SENSITIVE.sub("[redacted]", msg)
                record.args = ()
        except Exception:
            pass
        return True


def install_log_filter() -> None:
    """Attach the redaction filter to loggers AND their handlers.

    Filters on a logger only apply to records logged directly to it, not to records
    that propagate up from child loggers (e.g. the snps parser). Attaching to the
    emitting handlers — plus a root handler so the 'last resort' handler is never
    used — ensures redaction happens wherever a record is actually written."""
    filt = NoGenotypeLogFilter()
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", ""):
        logger = logging.getLogger(name)
        logger.addFilter(filt)
        for handler in logger.handlers:
            handler.addFilter(filt)
    # Cover the root's own handlers (where propagated records are emitted).
    for handler in root.handlers:
        handler.addFilter(filt)
