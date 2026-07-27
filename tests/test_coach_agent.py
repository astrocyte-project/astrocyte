"""CoachAgent tests (ADR-002/ADR-011): mocked LLM, real MCP + policy path."""

import json
from typing import Any

import httpx
import pytest

from astrocyte.agents.coach import (
    CoachAgent,
    build_coach_tools,
    default_agent_factory,
)
from astrocyte.core.llm import ModelRouter, ProviderSpec, ResolvedProvider
from astrocyte.core.policy import ActionTier, PolicyEngine, PolicyRule
from astrocyte.ha.client import HAClient
from astrocyte.ha.mcp import build_ha_mcp
from astrocyte.mcp.server import AstrocyteMCP

STATES = [
    {
        "entity_id": "sensor.house_battery_soc",
        "state": "87",
        "attributes": {
            "friendly_name": "House Battery SOC",
            "unit_of_measurement": "%",
        },
    },
    {
        "entity_id": "light.galley",
        "state": "off",
        "attributes": {"friendly_name": "Galley Light"},
    },
]


def ha_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/states":
        return httpx.Response(200, json=STATES)
    if request.url.path.startswith("/api/services/"):
        return httpx.Response(200, json=[{"entity_id": "light.galley"}])
    return httpx.Response(404)


@pytest.fixture
def mcp() -> AstrocyteMCP:
    client = HAClient(
        "http://ha.test:8123",
        "token",
        http=httpx.AsyncClient(
            base_url="http://ha.test:8123",
            transport=httpx.MockTransport(ha_handler),
        ),
    )
    policy = PolicyEngine(
        rules=(
            PolicyRule(tier=ActionTier.CONTROL, domain="light"),
            PolicyRule(tier=ActionTier.GUARDED, domain="water_heater"),
        )
    )
    return build_ha_mcp(client, policy)


def healthy_router() -> ModelRouter:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )

    return ModelRouter(
        providers=(
            ProviderSpec(
                name="gpu", endpoint="http://gpu:11434", model="qwen3:32b", priority=10
            ),
        ),
        client_factory=factory,
    )


def tool_by_name(tools: list[Any], name: str) -> Any:
    return next(t for t in tools if t.metadata.name == name)


@pytest.mark.anyio
async def test_tools_route_through_mcp_and_policy(mcp: AstrocyteMCP) -> None:
    """The full agent-tool -> MCP -> policy -> HA chain, no LLM required."""
    tools = build_coach_tools(mcp)
    names = {t.metadata.name for t in tools}
    assert names == {
        "rv_status",
        "list_entities",
        "get_state",
        "get_history",
        "get_statistics",
        "call_service",
    }

    status = json.loads(await tool_by_name(tools, "rv_status").async_fn())
    assert status["battery"][0]["entity_id"] == "sensor.house_battery_soc"

    allowed = json.loads(
        await tool_by_name(tools, "call_service").async_fn(
            domain="light", service="turn_on", entity_ids=["light.galley"]
        )
    )
    assert allowed["status"] == "executed"

    denied = json.loads(
        await tool_by_name(tools, "call_service").async_fn(
            domain="switch", service="turn_on", entity_ids=["switch.generator"]
        )
    )
    assert denied["status"] == "denied"  # default-deny policy

    guarded = json.loads(
        await tool_by_name(tools, "call_service").async_fn(
            domain="water_heater", service="turn_on"
        )
    )
    assert guarded["status"] == "pending_approval"
    assert guarded["approval_id"]


@pytest.mark.anyio
async def test_ask_uses_router_and_agent_factory(mcp: AstrocyteMCP) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(self, tools: list[Any]) -> None:
            self._tools = tools

        async def run(self, question: str) -> str:
            captured["question"] = question
            snapshot = await tool_by_name(self._tools, "rv_status").async_fn()
            soc = json.loads(snapshot)["battery"][0]["state"]
            return f"Battery is at {soc}%."

    def factory(provider: ResolvedProvider, tools: list[Any]) -> FakeAgent:
        captured["provider"] = provider
        return FakeAgent(tools)

    agent = CoachAgent(mcp, healthy_router(), agent_factory=factory)
    answer = await agent.ask("how is the battery?")
    assert answer == "Battery is at 87%."
    assert captured["question"] == "how is the battery?"
    assert captured["provider"].name == "gpu"  # routed, not hardcoded


def test_default_factory_builds_function_agent(mcp: AstrocyteMCP) -> None:
    """Real LlamaIndex wiring constructs (no LLM server needed to build)."""
    provider = ResolvedProvider(
        name="gpu", endpoint="http://gpu:11434", model="qwen3:32b"
    )
    agent = default_agent_factory(provider, build_coach_tools(mcp))
    assert type(agent).__name__ == "FunctionAgent"
