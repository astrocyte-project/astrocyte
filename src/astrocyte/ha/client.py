"""Home Assistant client (ADR-011): REST for state/history/services,
WebSocket for long-term statistics.

Both transports are injectable so tests run against ``httpx.MockTransport``
and a fake WebSocket — no HA instance required.
"""

from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

import httpx


class HAError(RuntimeError):
    """Home Assistant returned an error."""


class HAAuthError(HAError):
    """The long-lived access token was rejected."""


class _WebSocketLike(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


def _default_ws_connect(
    url: str,
) -> AbstractAsyncContextManager[_WebSocketLike]:  # pragma: no cover - network
    import websockets

    return websockets.connect(url)


class HAClient:
    """Async client for one Home Assistant instance."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        http: httpx.AsyncClient | None = None,
        ws_connect: (
            Any | None
        ) = None,  # Callable[[str], AsyncContextManager[_WebSocketLike]]
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._http = http or httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        self._ws_connect = ws_connect or _default_ws_connect

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- REST -----------------------------------------------------------------

    @staticmethod
    def _check(response: httpx.Response) -> httpx.Response:
        if response.status_code == httpx.codes.UNAUTHORIZED:
            msg = "Home Assistant rejected the access token"
            raise HAAuthError(msg)
        if response.is_error:
            msg = f"HA API error {response.status_code}: {response.text[:200]}"
            raise HAError(msg)
        return response

    async def get_states(self) -> list[dict[str, Any]]:
        response = self._check(await self._http.get("/api/states"))
        states: list[dict[str, Any]] = response.json()
        return states

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        response = await self._http.get(f"/api/states/{entity_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        state: dict[str, Any] = self._check(response).json()
        return state

    async def get_history(
        self, entity_id: str, start: str, end: str | None = None
    ) -> list[dict[str, Any]]:
        """Recorder raw history for one entity (ISO-8601 ``start``/``end``)."""
        params: dict[str, str] = {"filter_entity_id": entity_id}
        if end is not None:
            params["end_time"] = end
        response = self._check(
            await self._http.get(f"/api/history/period/{start}", params=params)
        )
        batches: list[list[dict[str, Any]]] = response.json()
        return batches[0] if batches else []

    async def call_service(
        self,
        domain: str,
        service: str,
        *,
        entity_ids: tuple[str, ...] = (),
        data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = dict(data or {})
        if entity_ids:
            body["entity_id"] = list(entity_ids)
        response = self._check(
            await self._http.post(f"/api/services/{domain}/{service}", json=body)
        )
        changed: list[dict[str, Any]] = response.json()
        return changed

    # --- WebSocket (long-term statistics) --------------------------------------

    @property
    def websocket_url(self) -> str:
        scheme = "wss" if self.base_url.startswith("https") else "ws"
        _, _, host = self.base_url.partition("://")
        return f"{scheme}://{host}/api/websocket"

    async def get_statistics(
        self,
        statistic_ids: list[str],
        *,
        start: str,
        end: str | None = None,
        period: str = "hour",
    ) -> dict[str, list[dict[str, Any]]]:
        """HA long-term statistics (hourly+ aggregates, kept indefinitely)."""
        async with self._ws_connect(self.websocket_url) as ws:
            await self._ws_auth(ws)
            request: dict[str, Any] = {
                "id": 1,
                "type": "recorder/statistics_during_period",
                "start_time": start,
                "statistic_ids": statistic_ids,
                "period": period,
            }
            if end is not None:
                request["end_time"] = end
            await ws.send(json.dumps(request))
            reply = json.loads(await ws.recv())
            if not reply.get("success"):
                msg = f"statistics query failed: {reply.get('error')}"
                raise HAError(msg)
            result: dict[str, list[dict[str, Any]]] = reply["result"]
            return result

    async def _ws_auth(self, ws: _WebSocketLike) -> None:
        hello = json.loads(await ws.recv())
        if hello.get("type") != "auth_required":  # pragma: no cover - protocol
            msg = f"unexpected websocket hello: {hello.get('type')}"
            raise HAError(msg)
        await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
        verdict = json.loads(await ws.recv())
        if verdict.get("type") != "auth_ok":
            msg = "Home Assistant rejected the access token (websocket)"
            raise HAAuthError(msg)
