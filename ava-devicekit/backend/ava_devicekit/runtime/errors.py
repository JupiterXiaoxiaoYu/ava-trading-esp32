from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ERROR_DEVICE_QUEUE_EXPIRED = "device.queue.expired"
ERROR_DEVICE_ACK_MISSING = "device.ack.missing"
ERROR_PROVIDER_ASR_TIMEOUT = "provider.asr.timeout"
ERROR_PROVIDER_LLM_ERROR = "provider.llm.error"
ERROR_PROVIDER_TTS_ERROR = "provider.tts.error"
ERROR_RUNTIME_STATE_INVALID = "runtime.state.invalid"
ERROR_RUNTIME_TASK_FAILED = "runtime.task.failed"

STANDARD_ERROR_CODES = frozenset(
    {
        ERROR_DEVICE_QUEUE_EXPIRED,
        ERROR_DEVICE_ACK_MISSING,
        ERROR_PROVIDER_ASR_TIMEOUT,
        ERROR_PROVIDER_LLM_ERROR,
        ERROR_PROVIDER_TTS_ERROR,
        ERROR_RUNTIME_STATE_INVALID,
        ERROR_RUNTIME_TASK_FAILED,
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeErrorInfo:
    """Serializable framework error envelope used by gateways and admin APIs."""

    code: str
    message: str
    component: str = "runtime"
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "component": self.component,
            "retryable": self.retryable,
            "details": dict(self.details),
        }


__all__ = [
    "ERROR_DEVICE_ACK_MISSING",
    "ERROR_DEVICE_QUEUE_EXPIRED",
    "ERROR_PROVIDER_ASR_TIMEOUT",
    "ERROR_PROVIDER_LLM_ERROR",
    "ERROR_PROVIDER_TTS_ERROR",
    "ERROR_RUNTIME_STATE_INVALID",
    "ERROR_RUNTIME_TASK_FAILED",
    "RuntimeErrorInfo",
    "STANDARD_ERROR_CODES",
]
