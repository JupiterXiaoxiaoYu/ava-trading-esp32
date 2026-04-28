from __future__ import annotations

from typing import Any

from ava_devicekit.control_plane.store import ControlPlaneStore
from ava_devicekit.runtime.settings import RuntimeSettings


def control_plane_usage_recorder(settings: RuntimeSettings):
    """Return a best-effort usage recorder for provider metering."""

    store = ControlPlaneStore(settings.control_plane_store_path)

    def record(device_id: str, metric: str, amount: float, source: str, metadata: dict[str, Any] | None = None) -> None:
        try:
            store.record_usage(
                {
                    "device_id": device_id,
                    "metric": metric,
                    "amount": amount,
                    "source": source,
                    "metadata": metadata or {},
                }
            )
        except Exception:
            # Metering should never break voice interaction. Devices that are
            # not yet provisioned can still run in lab mode.
            return

    return record
