"""End-to-end bridge test over a real vcan interface + MQTT broker (ADR-012).

Runs only where both a ``vcan0`` SocketCAN interface and an MQTT broker are
available (the `rvc-vcan` CI job provisions both; locally see
docs/development.md). Auto-skips everywhere else so `make test` stays green.
"""

import asyncio
import json
import os
import socket
from pathlib import Path

import pytest

pytestmark = pytest.mark.vcan

FIXTURE = Path(__file__).parent / "fixtures" / "rvc" / "coach-synthetic.log"
MQTT_HOST = os.environ.get("ASTROCYTE_TEST_MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("ASTROCYTE_TEST_MQTT_PORT", "1883"))


def _vcan_available() -> bool:
    try:
        import can

        bus = can.Bus(channel="vcan0", interface="socketcan")
        bus.shutdown()
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


def _broker_available() -> bool:
    try:
        with socket.create_connection((MQTT_HOST, MQTT_PORT), timeout=1):
            return True
    except OSError:
        return False


requires_env = pytest.mark.skipif(
    not (_vcan_available() and _broker_available()),
    reason="needs vcan0 + an MQTT broker (see the rvc-vcan CI job)",
)


@requires_env
@pytest.mark.anyio
async def test_bridge_replays_fixture_to_retained_topics() -> None:
    import aiomqtt
    import can
    from can.io import CanutilsLogReader

    from astrocyte.rvc.bridge import BridgeSettings, RvcBridge

    settings = BridgeSettings(
        can_channel="vcan0",
        mqtt_url=f"mqtt://{MQTT_HOST}:{MQTT_PORT}",
        coach_id="vcantest",
    )
    bridge = RvcBridge(settings)
    bridge_task = asyncio.create_task(bridge.run())
    try:
        await asyncio.sleep(0.5)  # bridge subscribes + publishes availability

        # Replay the fixture onto the bus from a second socket.
        with (
            can.Bus(channel="vcan0", interface="socketcan") as sender,
            CanutilsLogReader(FIXTURE) as reader,
        ):
            for message in reader:
                sender.send(message)
                await asyncio.sleep(0.02)
        await asyncio.sleep(0.5)

        # A fresh subscriber must see retained discovery + state + status.
        expected = {
            "rvc/bridge/status": "online",
            "rvc/state/tank_status/0": None,
            "homeassistant/device/rvc_vcantest_tank_status_0/config": None,
            "rvc/state/thermostat_status_1/1": None,
        }
        seen: dict[str, str] = {}
        async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
            await client.subscribe("rvc/#")
            await client.subscribe("homeassistant/#")
            async with asyncio.timeout(5):
                async for message in client.messages:
                    payload = message.payload
                    assert isinstance(payload, bytes)
                    seen[str(message.topic)] = payload.decode()
                    if set(expected) <= set(seen):
                        break

        assert seen["rvc/bridge/status"] == "online"
        tank = json.loads(seen["rvc/state/tank_status/0"])
        assert tank["instance_label"] == "fresh water"
        thermostat = json.loads(seen["rvc/state/thermostat_status_1/1"])
        assert thermostat["setpoint_temp_cool"] == 24.0
        discovery = json.loads(
            seen["homeassistant/device/rvc_vcantest_tank_status_0/config"]
        )
        assert discovery["components"]["relative_level"]["platform"] == "sensor"
    finally:
        bridge_task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await bridge_task
