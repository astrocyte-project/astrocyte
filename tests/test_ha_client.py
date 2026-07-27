"""HAClient tests against httpx.MockTransport + a fake websocket."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from astrocyte.ha import HAAuthError, HAClient, HAError

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
        "state": "on",
        "attributes": {"friendly_name": "Galley Light"},
    },
]


def make_client(handler: httpx.MockTransport) -> HAClient:
    http = httpx.AsyncClient(base_url="http://ha.test:8123", transport=handler)
    return HAClient("http://ha.test:8123", "token123", http=http)


@pytest.mark.anyio
async def test_get_states() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states"
        return httpx.Response(200, json=STATES)

    client = make_client(httpx.MockTransport(handler))
    assert await client.get_states() == STATES


@pytest.mark.anyio
async def test_get_state_found_and_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("light.galley"):
            return httpx.Response(200, json=STATES[1])
        return httpx.Response(404)

    client = make_client(httpx.MockTransport(handler))
    assert await client.get_state("light.galley") == STATES[1]
    assert await client.get_state("light.nope") is None


@pytest.mark.anyio
async def test_auth_error() -> None:
    client = make_client(httpx.MockTransport(lambda _: httpx.Response(401)))
    with pytest.raises(HAAuthError):
        await client.get_states()


@pytest.mark.anyio
async def test_server_error() -> None:
    client = make_client(
        httpx.MockTransport(lambda _: httpx.Response(500, text="boom"))
    )
    with pytest.raises(HAError, match="500"):
        await client.get_states()


@pytest.mark.anyio
async def test_get_history_flattens_first_batch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/api/history/period/2026-07-01")
        assert request.url.params["filter_entity_id"] == "sensor.x"
        return httpx.Response(200, json=[[{"state": "1"}, {"state": "2"}]])

    client = make_client(httpx.MockTransport(handler))
    history = await client.get_history("sensor.x", "2026-07-01T00:00:00Z")
    assert [h["state"] for h in history] == ["1", "2"]


@pytest.mark.anyio
async def test_call_service_posts_entities() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[{"entity_id": "light.galley"}])

    client = make_client(httpx.MockTransport(handler))
    changed = await client.call_service(
        "light", "turn_on", entity_ids=("light.galley",), data={"brightness": 128}
    )
    assert captured["path"] == "/api/services/light/turn_on"
    assert captured["body"] == {"brightness": 128, "entity_id": ["light.galley"]}
    assert len(changed) == 1


class FakeWebSocket:
    """Scripted HA websocket: auth handshake + one statistics reply."""

    def __init__(self, auth_ok: bool = True, success: bool = True) -> None:
        self.sent: list[str] = []
        auth_reply = {"type": "auth_ok" if auth_ok else "auth_invalid"}
        result = {
            "id": 1,
            "success": success,
            "result": {"sensor.house_battery_soc": [{"mean": 85.2}]},
            "error": None if success else {"code": "bad"},
        }
        self._replies = [
            json.dumps({"type": "auth_required"}),
            json.dumps(auth_reply),
            json.dumps(result),
        ]

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        return self._replies.pop(0)


def fake_ws_connect(ws: FakeWebSocket) -> object:
    @asynccontextmanager
    async def connect(url: str) -> AsyncIterator[FakeWebSocket]:
        assert url == "ws://ha.test:8123/api/websocket"
        yield ws

    return connect


@pytest.mark.anyio
async def test_get_statistics() -> None:
    ws = FakeWebSocket()
    client = HAClient(
        "http://ha.test:8123",
        "token123",
        http=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(500))
        ),
        ws_connect=fake_ws_connect(ws),
    )
    stats = await client.get_statistics(
        ["sensor.house_battery_soc"], start="2026-07-01T00:00:00Z", period="hour"
    )
    assert stats["sensor.house_battery_soc"][0]["mean"] == 85.2
    auth_message = json.loads(ws.sent[0])
    assert auth_message == {"type": "auth", "access_token": "token123"}
    query = json.loads(ws.sent[1])
    assert query["type"] == "recorder/statistics_during_period"
    assert query["period"] == "hour"


@pytest.mark.anyio
async def test_get_statistics_auth_rejected() -> None:
    client = HAClient(
        "http://ha.test:8123",
        "bad",
        http=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(500))
        ),
        ws_connect=fake_ws_connect(FakeWebSocket(auth_ok=False)),
    )
    with pytest.raises(HAAuthError):
        await client.get_statistics(["sensor.x"], start="2026-07-01T00:00:00Z")


@pytest.mark.anyio
async def test_get_statistics_query_failure() -> None:
    client = HAClient(
        "http://ha.test:8123",
        "token123",
        http=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(500))
        ),
        ws_connect=fake_ws_connect(FakeWebSocket(success=False)),
    )
    with pytest.raises(HAError, match="statistics"):
        await client.get_statistics(["sensor.x"], start="2026-07-01T00:00:00Z")


def test_websocket_url_schemes() -> None:
    http = HAClient("http://ha.test:8123", "t")
    https = HAClient("https://ha.example.com", "t")
    assert http.websocket_url == "ws://ha.test:8123/api/websocket"
    assert https.websocket_url == "wss://ha.example.com/api/websocket"
