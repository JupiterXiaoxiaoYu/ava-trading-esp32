from __future__ import annotations

import json
import os
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse

from ava_devicekit.services.registry import DeveloperService, find_developer_service

SAFE_METHODS = {"GET", "POST"}


def invoke_developer_service(services: list[dict[str, Any]] | list[DeveloperService], service_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Invoke an explicitly allowlisted developer service from the backend.

    This is an admin/app-side escape hatch, not a device-side arbitrary proxy.
    A service must set `invocable: true` and list allowed paths.
    """

    service = find_developer_service(services, service_id)
    if not service:
        raise ValueError(f"unknown developer service: {service_id}")
    if not bool(service.options.get("invocable")):
        raise PermissionError(f"developer service is not invocable: {service_id}")
    allowed_paths = [str(item) for item in service.options.get("allowed_paths", [])] if isinstance(service.options.get("allowed_paths"), list) else []
    path = str(request.get("path") or "/")
    if not allowed_paths or path not in allowed_paths:
        raise PermissionError(f"path is not allowlisted for service {service_id}: {path}")
    method = str(request.get("method") or "POST").upper()
    if method not in SAFE_METHODS:
        raise PermissionError(f"method is not supported for service invocation: {method}")
    base_url = str(service.base_url or "").rstrip("/") + "/"
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"service base_url must be http(s): {service_id}")
    body = request.get("body") if isinstance(request.get("body"), dict) else {}
    headers = {"Content-Type": "application/json"}
    if service.api_key_env and os.environ.get(service.api_key_env):
        headers[str(service.options.get("auth_header") or "Authorization")] = str(service.options.get("auth_prefix") or "Bearer ") + os.environ[service.api_key_env]
    data = None if method == "GET" else json.dumps(body).encode("utf-8")
    timeout = float(service.options.get("timeout_sec") or 10)
    req = urllib.request.Request(urljoin(base_url, path.lstrip("/")), data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type.lower():
            parsed_body: Any = json.loads(raw.decode("utf-8")) if raw else None
        else:
            parsed_body = raw.decode("utf-8", errors="replace")
        return {"ok": 200 <= resp.status < 300, "status": resp.status, "service_id": service.service_id, "body": parsed_body}
