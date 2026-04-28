from __future__ import annotations

from ava_devicekit.gateway.server import create_devicekit_server
from ava_devicekit.runtime.settings import RuntimeSettings


def test_create_devicekit_server_wires_shared_runtime(tmp_path):
    settings = RuntimeSettings.from_dict({"host": "127.0.0.1", "http_port": 0, "runtime_state_dir": str(tmp_path / "runtime-state")})

    server = create_devicekit_server(settings=settings, mock=True, skill_store_path=str(tmp_path / "skills"))

    try:
        assert server.manager.boot("device-a")["screen"] == "feed"
        assert "connection_sweep" in server.task_manager.names
        health = server.http_server.RequestHandlerClass
        assert health is not None
    finally:
        server.http_server.server_close()
