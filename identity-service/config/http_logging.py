"""Helpers for verbose HTTP request and response logging in development."""

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse


LOGGER = logging.getLogger("alt_identity.http")


def _is_enabled() -> bool:
    """Return whether verbose ALT-Identity HTTP logging is enabled."""
    return getattr(settings, "ALT_IDENTITY_VERBOSE_HTTP_LOGGING", True)


def _safe_json(value: Any) -> str:
    """Serialize a value for log output with a readable fallback."""
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return repr(value)


def _request_payload(request: HttpRequest) -> dict[str, Any]:
    """Extract a log-friendly request payload snapshot."""
    if request.method in {"POST", "PUT", "PATCH"}:
        return {key: request.POST.getlist(key) for key in request.POST}

    return {key: request.GET.getlist(key) for key in request.GET}


def log_inbound_request(request: HttpRequest, *, extra: dict[str, Any] | None = None) -> None:
    """Log an inbound Django request handled by this project."""
    if not _is_enabled():
        return

    payload = {
        "kind": "inbound_request",
        "method": request.method,
        "path": request.path,
        "query_string": request.META.get("QUERY_STRING", ""),
        "payload": _request_payload(request),
        "headers": {
            "Authorization": request.headers.get("Authorization"),
            "Content-Type": request.headers.get("Content-Type"),
        },
        "user": getattr(request.user, "username", None) if getattr(request, "user", None) and request.user.is_authenticated else None,
    }
    if extra:
        payload.update(extra)

    LOGGER.info(_safe_json(payload))


def log_outbound_request(
    method: str,
    url: str,
    *,
    headers: dict[str, Any] | None = None,
    body: dict[str, Any] | str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log an outbound HTTP request sent by the demo client."""
    if not _is_enabled():
        return

    payload = {
        "kind": "outbound_request",
        "method": method,
        "url": url,
        "headers": headers or {},
        "body": body,
    }
    if extra:
        payload.update(extra)

    LOGGER.info(_safe_json(payload))


def log_response(
    response: HttpResponse,
    *,
    source: str,
    extra: dict[str, Any] | None = None,
) -> HttpResponse:
    """Log an HTTP response and return it unchanged."""
    if not _is_enabled():
        return response

    content = response.content.decode("utf-8", errors="replace") if response.content else ""
    payload = {
        "kind": "response",
        "source": source,
        "status_code": response.status_code,
        "content_type": response.get("Content-Type"),
        "headers": dict(response.items()),
        "body": content,
    }
    if extra:
        payload.update(extra)

    LOGGER.info(_safe_json(payload))
    return response


def log_outbound_response(
    *,
    method: str,
    url: str,
    status_code: int,
    body: str,
    headers: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log an outbound HTTP response received by the demo client."""
    if not _is_enabled():
        return

    payload = {
        "kind": "outbound_response",
        "method": method,
        "url": url,
        "status_code": status_code,
        "headers": headers or {},
        "body": body,
    }
    if extra:
        payload.update(extra)

    LOGGER.info(_safe_json(payload))
