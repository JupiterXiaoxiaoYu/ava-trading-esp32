from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.http_server import make_handler
from ava_devicekit.gateway.legacy_firmware import run_legacy_firmware_gateway
from ava_devicekit.gateway.runtime_manager import RuntimeManager, runtime_manager_for_settings
from ava_devicekit.providers.health import provider_health_report
from ava_devicekit.providers.registry import ProviderBundle, create_provider_bundle
from ava_devicekit.runtime.errors import ERROR_RUNTIME_TASK_FAILED, RuntimeErrorInfo
from ava_devicekit.runtime.settings import RuntimeSettings
from ava_devicekit.runtime.tasks import BackgroundTaskManager, TaskEvent


@dataclass(slots=True)
class DeviceKitServer:
    """Single-process runtime that shares one manager across HTTP, WS and tasks."""

    settings: RuntimeSettings
    manager: RuntimeManager
    providers: ProviderBundle
    task_manager: BackgroundTaskManager
    http_server: ThreadingHTTPServer
    http_thread: threading.Thread | None = None

    async def start(self) -> None:
        self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True, name="ava-devicekit-http")
        self.http_thread.start()
        await self.task_manager.start()
        print(f"Ava DeviceKit HTTP gateway listening on http://{self.settings.host}:{self.settings.http_port}")
        print(f"Ava DeviceKit legacy WS gateway listening on ws://{self.settings.host}:{self.settings.websocket_port}/ava/v1/")
        try:
            await run_legacy_firmware_gateway(
                self.settings.host,
                self.settings.websocket_port,
                runtime_settings=self.settings,
                manager=self.manager,
                providers=self.providers,
            )
        finally:
            await self.stop()

    async def stop(self) -> None:
        await self.task_manager.stop()
        self.http_server.shutdown()
        self.http_server.server_close()
        if self.http_thread:
            self.http_thread.join(timeout=5)


def create_devicekit_server(
    *,
    settings: RuntimeSettings | None = None,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
) -> DeviceKitServer:
    settings = settings or RuntimeSettings.load()
    manager = runtime_manager_for_settings(
        settings,
        app_id=app_id,
        manifest_path=manifest_path,
        adapter=adapter,
        mock=mock,
        skill_store_path=skill_store_path,
        queue_outbound=False,
    )
    providers = create_provider_bundle(settings)
    task_manager = _create_task_manager(manager, settings)
    handler = make_handler(
        runtime_settings=settings,
        manager=manager,
        task_manager=task_manager,
        provider_health=lambda: provider_health_report(settings),
    )
    http_server = ThreadingHTTPServer((settings.host, settings.http_port), handler)
    return DeviceKitServer(settings=settings, manager=manager, providers=providers, task_manager=task_manager, http_server=http_server)


def run_server(
    *,
    settings: RuntimeSettings | None = None,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
) -> None:
    server = create_devicekit_server(
        settings=settings,
        app_id=app_id,
        manifest_path=manifest_path,
        adapter=adapter,
        mock=mock,
        skill_store_path=skill_store_path,
    )
    asyncio.run(server.start())


def _create_task_manager(manager: RuntimeManager, settings: RuntimeSettings) -> BackgroundTaskManager:
    def on_task_event(event: TaskEvent) -> None:
        if event.type != "tick_failed":
            return
        error = RuntimeErrorInfo(
            code=ERROR_RUNTIME_TASK_FAILED,
            message=f"background task failed: {event.name}",
            component="runtime.tasks",
            retryable=True,
            details={"task": event.name, "exception": str(event.exception) if event.exception else ""},
        )
        manager.event_bus.runtime_error("runtime", error.to_dict())

    task_manager = BackgroundTaskManager(event_callback=on_task_event)
    idle_limit = max(float(settings.websocket_ping_interval + settings.websocket_ping_timeout) * 3.0, 120.0)
    task_manager.add_periodic(
        "connection_sweep",
        interval=30.0,
        initial_delay=30.0,
        callback=lambda: manager.sweep_stale_connections(max_idle_sec=idle_limit),
        backoff_base=5.0,
        max_backoff=60.0,
    )
    return task_manager


__all__ = ["DeviceKitServer", "create_devicekit_server", "run_server"]
