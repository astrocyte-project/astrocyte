"""ModelRouter tests (ADR-013): priority, fallback, probe caching."""

from pathlib import Path

import httpx
import pytest

from astrocyte.core.llm import (
    ModelRouter,
    NoProviderAvailableError,
    ProviderSpec,
    ResolvedProvider,
)

GPU = ProviderSpec(
    name="gpu",
    endpoint="http://gpu:11434",
    model="qwen3:32b",
    priority=10,
    capabilities=frozenset({"chat", "heavy"}),
)
COACH = ProviderSpec(
    name="coach",
    endpoint="http://coach:11434",
    model="llama3.2:3b",
    priority=50,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_router(
    healthy: set[str], clock: FakeClock | None = None
) -> tuple[ModelRouter, list[str]]:
    """Router whose probes succeed only for hosts in ``healthy``."""
    probed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        probed.append(request.url.host)
        if request.url.host in healthy:
            return httpx.Response(200)
        raise httpx.ConnectError("down", request=request)

    def client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    router = ModelRouter(
        providers=(COACH, GPU),  # deliberately unsorted; router sorts by priority
        client_factory=client_factory,
        clock=clock if clock is not None else FakeClock(),
    )
    return router, probed


@pytest.mark.anyio
async def test_routes_to_gpu_when_healthy() -> None:
    router, _ = make_router(healthy={"gpu", "coach"})
    resolved = await router.route("chat")
    assert resolved == ResolvedProvider(
        name="gpu", endpoint="http://gpu:11434", model="qwen3:32b"
    )


@pytest.mark.anyio
async def test_falls_back_to_coach_when_gpu_down() -> None:
    router, _ = make_router(healthy={"coach"})
    resolved = await router.route("chat")
    assert resolved.name == "coach"


@pytest.mark.anyio
async def test_capability_filter() -> None:
    router, _ = make_router(healthy={"coach"})
    # Only the (down) GPU node offers `heavy`.
    with pytest.raises(NoProviderAvailableError, match="heavy"):
        await router.route("heavy")


@pytest.mark.anyio
async def test_no_provider_at_all() -> None:
    router, _ = make_router(healthy=set())
    with pytest.raises(NoProviderAvailableError):
        await router.route("chat")


@pytest.mark.anyio
async def test_probe_results_are_cached_within_ttl() -> None:
    clock = FakeClock()
    router, probed = make_router(healthy={"gpu"}, clock=clock)
    await router.route("chat")
    await router.route("chat")
    assert probed.count("gpu") == 1  # second call served from cache

    clock.now += router.probe_ttl_seconds + 1
    await router.route("chat")
    assert probed.count("gpu") == 2  # cache expired, re-probed


def test_from_file(tmp_path: Path) -> None:
    models = tmp_path / "models.yml"
    models.write_text(
        """
probe_ttl_seconds: 5
providers:
  - name: gpu
    endpoint: http://gpu:11434/
    model: qwen3:32b
    priority: 10
    capabilities: [chat, heavy]
  - name: coach
    endpoint: http://coach:11434
    model: llama3.2:3b
"""
    )
    router = ModelRouter.from_file(models)
    assert router.probe_ttl_seconds == 5
    assert [p.name for p in router.providers] == ["gpu", "coach"]
    assert router.providers[0].endpoint == "http://gpu:11434"  # trailing / stripped
    assert router.providers[1].capabilities == frozenset({"chat"})


def test_from_file_rejects_non_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "models.yml"
    bad.write_text("- nope\n")
    with pytest.raises(ValueError, match="mapping"):
        ModelRouter.from_file(bad)
