"""HA MCP server tests (ADR-011/ADR-014) via an in-memory FastMCP client."""

import json
from typing import Any

import httpx
import pytest
from fastmcp import Client

from astrocyte.core.policy import (
    ActionTier,
    ApprovalStatus,
    PolicyEngine,
    PolicyRule,
)
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
            "device_class": "battery",
        },
    },
    {
        "entity_id": "light.galley",
        "state": "on",
        "attributes": {"friendly_name": "Galley Light"},
    },
    {
        "entity_id": "switch.generator",
        "state": "off",
        "attributes": {"friendly_name": "Generator"},
    },
]


class RecordingHandler:
    def __init__(self) -> None:
        self.service_calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/states":
            return httpx.Response(200, json=STATES)
        if path.startswith("/api/services/"):
            self.service_calls.append((path, json.loads(request.content or b"{}")))
            return httpx.Response(200, json=[{"entity_id": "light.galley"}])
        if path.startswith("/api/history/"):
            return httpx.Response(200, json=[[{"state": "87"}]])
        return httpx.Response(404)


@pytest.fixture
def handler() -> RecordingHandler:
    return RecordingHandler()


@pytest.fixture
def server(handler: RecordingHandler) -> AstrocyteMCP:
    client = HAClient(
        "http://ha.test:8123",
        "token123",
        http=httpx.AsyncClient(
            base_url="http://ha.test:8123", transport=httpx.MockTransport(handler)
        ),
    )
    policy = PolicyEngine(
        rules=(
            PolicyRule(tier=ActionTier.DENY, targets=("switch.generator",)),
            PolicyRule(tier=ActionTier.CONTROL, domain="light"),
            PolicyRule(tier=ActionTier.GUARDED, domain="water_heater"),
        )
    )
    return build_ha_mcp(client, policy)


def result_data(result: Any) -> Any:
    return result.data


@pytest.mark.anyio
async def test_tool_listing(server: AstrocyteMCP) -> None:
    async with Client(server.server) as client:
        tools = {tool.name for tool in await client.list_tools()}
    assert tools == {
        "list_entities",
        "get_state",
        "get_history",
        "get_statistics",
        "call_service",
        "rv_status",
        "list_pending_approvals",
    }


@pytest.mark.anyio
async def test_list_entities_filters(server: AstrocyteMCP) -> None:
    async with Client(server.server) as client:
        result = await client.call_tool("list_entities", {"domain": "light"})
    entities = result_data(result)
    assert [e["entity_id"] for e in entities] == ["light.galley"]
    assert entities[0]["name"] == "Galley Light"


@pytest.mark.anyio
async def test_call_service_control_executes(
    server: AstrocyteMCP, handler: RecordingHandler
) -> None:
    async with Client(server.server) as client:
        result = await client.call_tool(
            "call_service",
            {
                "domain": "light",
                "service": "turn_on",
                "entity_ids": ["light.galley"],
                "data": {"brightness": 200},
            },
        )
    payload = result_data(result)
    assert payload["status"] == "executed"
    assert payload["tier"] == "control"
    assert handler.service_calls == [
        (
            "/api/services/light/turn_on",
            {"brightness": 200, "entity_id": ["light.galley"]},
        )
    ]


@pytest.mark.anyio
async def test_call_service_denied(
    server: AstrocyteMCP, handler: RecordingHandler
) -> None:
    async with Client(server.server) as client:
        result = await client.call_tool(
            "call_service",
            {
                "domain": "switch",
                "service": "turn_on",
                "entity_ids": ["switch.generator"],
            },
        )
    payload = result_data(result)
    assert payload["status"] == "denied"
    assert handler.service_calls == []  # HA never touched


@pytest.mark.anyio
async def test_call_service_guarded_round_trip(
    server: AstrocyteMCP, handler: RecordingHandler
) -> None:
    async with Client(server.server) as client:
        pending = result_data(
            await client.call_tool(
                "call_service",
                {
                    "domain": "water_heater",
                    "service": "turn_on",
                    "entity_ids": ["water_heater.main"],
                },
            )
        )
        assert pending["status"] == "pending_approval"
        approval_id = pending["approval_id"]

        # The pending approval was mirrored into HA as a notification.
        notification_calls = [
            call
            for call in handler.service_calls
            if call[0] == "/api/services/persistent_notification/create"
        ]
        assert len(notification_calls) == 1
        assert approval_id in notification_calls[0][1]["message"]

        listed = result_data(await client.call_tool("list_pending_approvals", {}))
        assert [a["approval_id"] for a in listed] == [approval_id]

        server.policy.store.set_status(approval_id, ApprovalStatus.APPROVED)
        executed = result_data(
            await client.call_tool(
                "call_service",
                {
                    "domain": "water_heater",
                    "service": "turn_on",
                    "entity_ids": ["water_heater.main"],
                    "approval_token": approval_id,
                },
            )
        )
        assert executed["status"] == "executed"
        assert executed["tier"] == "guarded"


@pytest.mark.anyio
async def test_rv_status_snapshot(server: AstrocyteMCP) -> None:
    async with Client(server.server) as client:
        snapshot = result_data(await client.call_tool("rv_status", {}))
    assert snapshot["lights_on"] == 1
    battery_ids = {e["entity_id"] for e in snapshot["battery"]}
    assert "sensor.house_battery_soc" in battery_ids
    power_ids = {e["entity_id"] for e in snapshot["power"]}
    assert "switch.generator" in power_ids
