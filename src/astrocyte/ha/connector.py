"""Home Assistant DataConnector — the first real connector (seeds #18)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrocyte.core.connector import DataConnector, Document
from astrocyte.ha.client import HAClient


def _entity_text(state: dict[str, Any]) -> str:
    attributes = state.get("attributes", {})
    name = attributes.get("friendly_name", state.get("entity_id", "unknown"))
    unit = attributes.get("unit_of_measurement")
    value = state.get("state", "unknown")
    return f"{name} is {value} {unit}".strip() if unit else f"{name} is {value}"


class HomeAssistantConnector(DataConnector):
    """Turns the HA entity population into ingestible documents."""

    connector_id = "home-assistant"

    def __init__(self, client: HAClient) -> None:
        self._client = client

    async def fetch(self) -> AsyncIterator[Document]:
        for state in await self._client.get_states():
            entity_id = str(state.get("entity_id", ""))
            if not entity_id:
                continue
            yield Document(
                doc_id=entity_id,
                text=_entity_text(state),
                source=f"ha://{entity_id}",
                metadata={
                    "domain": entity_id.split(".", 1)[0],
                    "state": state.get("state"),
                    "last_changed": state.get("last_changed"),
                },
            )

    async def discover(self) -> dict[str, str]:
        states = await self._client.get_states()
        return {
            "connector_id": self.connector_id,
            "base_url": self._client.base_url,
            "entity_count": str(len(states)),
        }
