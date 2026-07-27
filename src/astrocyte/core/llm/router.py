"""Model routing across nodes (ADR-013).

The coach's GPU workstation is on-demand: routing walks providers in priority
order and picks the first healthy one, so agents get the big model when the
workstation is up and degrade to the coach node's small model (or fail fast
with a typed error) when it isn't. Health probes are cached briefly so a
powered-off node costs one timeout, not one per call.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml


class NoProviderAvailableError(RuntimeError):
    """No healthy provider offers the requested capability."""


@dataclass(frozen=True)
class ProviderSpec:
    """One inference endpoint (typically an Ollama instance)."""

    name: str
    endpoint: str
    model: str
    priority: int = 100  # lower wins
    capabilities: frozenset[str] = frozenset({"chat"})
    probe_path: str = "/api/tags"  # Ollama liveness endpoint
    probe_timeout: float = 2.0


@dataclass(frozen=True)
class ResolvedProvider:
    """The routing result handed to callers."""

    name: str
    endpoint: str
    model: str


@dataclass
class ModelRouter:
    providers: tuple[ProviderSpec, ...] = ()
    probe_ttl_seconds: float = 15.0
    clock: Callable[[], float] = time.monotonic
    # Injectable for tests (e.g. MockTransport-backed clients).
    client_factory: Callable[[], httpx.AsyncClient] = httpx.AsyncClient
    _probe_cache: dict[str, tuple[float, bool]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.providers = tuple(sorted(self.providers, key=lambda p: p.priority))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRouter:
        providers = tuple(
            ProviderSpec(
                name=str(raw["name"]),
                endpoint=str(raw["endpoint"]).rstrip("/"),
                model=str(raw["model"]),
                priority=int(raw.get("priority", 100)),
                capabilities=frozenset(
                    str(c) for c in raw.get("capabilities", ["chat"])
                ),
                probe_path=str(raw.get("probe_path", "/api/tags")),
                probe_timeout=float(raw.get("probe_timeout", 2.0)),
            )
            for raw in data.get("providers", [])
        )
        return cls(
            providers=providers,
            probe_ttl_seconds=float(data.get("probe_ttl_seconds", 15)),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> ModelRouter:
        with Path(path).open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            msg = f"models file must be a mapping: {path}"
            raise ValueError(msg)
        return cls.from_dict(data)

    async def route(self, capability: str = "chat") -> ResolvedProvider:
        """Return the highest-priority healthy provider for ``capability``."""
        candidates = [p for p in self.providers if capability in p.capabilities]
        for provider in candidates:
            if await self._healthy(provider):
                return ResolvedProvider(
                    name=provider.name,
                    endpoint=provider.endpoint,
                    model=provider.model,
                )
        names = ", ".join(p.name for p in candidates) or "<none configured>"
        msg = f"no healthy provider for capability {capability!r} (tried: {names})"
        raise NoProviderAvailableError(msg)

    async def _healthy(self, provider: ProviderSpec) -> bool:
        now = self.clock()
        cached = self._probe_cache.get(provider.name)
        if cached is not None and now - cached[0] < self.probe_ttl_seconds:
            return cached[1]
        ok = False
        try:
            async with self.client_factory() as client:
                response = await client.get(
                    provider.endpoint + provider.probe_path,
                    timeout=provider.probe_timeout,
                )
            ok = response.status_code == 200
        except httpx.HTTPError:
            ok = False
        self._probe_cache[provider.name] = (now, ok)
        return ok
