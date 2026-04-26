from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ModelRoute:
    provider: str
    model: str
    mode: str


class ModelRouter:
    """Small model routing policy holder.

    Actual ASR/LLM/TTS providers are injected by deployments. The framework only
    records the route so apps do not hardcode vendor-specific clients.
    """

    def __init__(self, routes: dict[str, ModelRoute] | None = None):
        self.routes = routes or {}

    def set_route(self, purpose: str, provider: str, model: str, mode: str = "default") -> None:
        self.routes[purpose] = ModelRoute(provider=provider, model=model, mode=mode)

    def get_route(self, purpose: str) -> ModelRoute | None:
        return self.routes.get(purpose)
