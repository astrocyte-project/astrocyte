"""HomeAssistantConnector tests: entity snapshots -> Documents."""

import httpx
import pytest

from astrocyte.ha import HAClient, HomeAssistantConnector

STATES = [
    {
        "entity_id": "sensor.fresh_water_tank",
        "state": "50",
        "attributes": {
            "friendly_name": "Fresh Water Tank",
            "unit_of_measurement": "%",
        },
        "last_changed": "2026-07-02T12:00:00Z",
    },
    {"entity_id": "light.galley", "state": "on", "attributes": {}},
    {"state": "orphan"},  # no entity_id: skipped
]


def make_connector() -> HomeAssistantConnector:
    http = httpx.AsyncClient(
        base_url="http://ha.test:8123",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=STATES)),
    )
    return HomeAssistantConnector(HAClient("http://ha.test:8123", "token", http=http))


@pytest.mark.anyio
async def test_fetch_yields_documents() -> None:
    docs = [doc async for doc in make_connector().fetch()]
    assert [d.doc_id for d in docs] == ["sensor.fresh_water_tank", "light.galley"]
    assert docs[0].text == "Fresh Water Tank is 50 %"
    assert docs[0].source == "ha://sensor.fresh_water_tank"
    assert docs[0].metadata["domain"] == "sensor"
    assert docs[1].text == "light.galley is on"


@pytest.mark.anyio
async def test_discover_counts_entities() -> None:
    info = await make_connector().discover()
    assert info["connector_id"] == "home-assistant"
    assert info["entity_count"] == "3"
