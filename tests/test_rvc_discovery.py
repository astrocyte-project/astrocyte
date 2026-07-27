"""Discovery-builder tests (ADR-011/ADR-012): golden shapes, unique_id stability."""

import json

import pytest

from astrocyte.rvc import DecodedMessage, RvcDecoder
from astrocyte.rvc.decoder import make_can_id
from astrocyte.rvc.discovery import DiscoveryBuilder
from astrocyte.rvc.instances import InstanceMap

TANK_FRAME = (make_can_id(0x1FFB7, 0x80), bytes.fromhex("000204FFFFFFFFFF"))
COMMAND_FRAME = (make_can_id(0x1FEDB, 0x82), bytes.fromhex("0CFF960000FFFFFF"))
THERMOSTAT_FRAME = (make_can_id(0x1FFE2, 0x80), bytes.fromhex("0021640B0C0000FF"))
AMBIENT_FRAME = (make_can_id(0x1FF9C, 0x80), bytes.fromhex("00A00BFFFFFFFFFF"))

NAMED_MAP = InstanceMap.from_dict(
    {
        "lights": {
            "living_room_ceiling": {
                "name": "Ceiling",
                "area": "Living Room",
                "command_instance": 70,
            }
        },
        "ac_zones": {0: {"name": "Front AC", "area": "Living Room"}},
    }
)


@pytest.fixture(scope="module")
def decoder() -> RvcDecoder:
    return RvcDecoder()


@pytest.fixture
def builder() -> DiscoveryBuilder:
    return DiscoveryBuilder(coach_id="refcoach", availability_topic="rvc/bridge/status")


def decode(decoder: RvcDecoder, frame: tuple[int, bytes]) -> DecodedMessage:
    return decoder.decode(*frame)


def test_tank_device_payload(decoder: RvcDecoder, builder: DiscoveryBuilder) -> None:
    publish = builder.build(decode(decoder, TANK_FRAME))
    assert publish is not None
    assert publish.retain
    assert publish.topic == "homeassistant/device/rvc_refcoach_tank_status_0/config"

    payload = json.loads(publish.payload)
    assert payload["device"]["identifiers"] == ["rvc_refcoach_tank_status_0"]
    assert payload["origin"]["name"] == "astrocyte-rvc-bridge"
    assert payload["availability_topic"] == "rvc/bridge/status"

    level = payload["components"]["relative_level"]
    assert level["platform"] == "sensor"
    assert level["state_topic"] == "rvc/state/tank_status/0"
    assert level["value_template"] == "{{ value_json.relative_level }}"
    # instance is identity, not telemetry
    assert "instance" not in payload["components"]


def test_lights_built_from_command_map() -> None:
    """Lights come from the command-instance map, not from any bus message."""
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status", instances=NAMED_MAP
    )
    pubs = builder.light_discoveries()
    assert len(pubs) == 1
    assert pubs[0].topic == "homeassistant/device/rvc_refcoach_light_70/config"
    payload = json.loads(pubs[0].payload)
    assert payload["device"]["name"] == "Ceiling"
    assert payload["device"]["suggested_area"] == "Living Room"
    light = payload["components"]["light"]
    assert light["platform"] == "light"
    assert light["unique_id"] == "rvc_refcoach_light_70_light"
    assert light["state_topic"] == "rvc/state/light/70"
    assert light["command_topic"] == "rvc/cmd/light/70/switch"
    assert light["brightness_command_topic"] == "rvc/cmd/light/70/brightness"


def test_light_entity_takes_the_device_name() -> None:
    """`name: null` is load-bearing — it is what keeps HA from doubling names.

    Naming the component renders "<device> <entity>" ("Ceiling Ceiling") and
    omitting the key entirely falls back to the platform class name ("MQTT
    LightEntity"); only an explicit null makes the entity take the device name.
    Both alternatives were confirmed against a live HA 2026.6 (issue #151).
    """
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status", instances=NAMED_MAP
    )
    light = json.loads(builder.light_discoveries()[0].payload)["components"]["light"]
    assert "name" in light
    assert light["name"] is None


def test_light_discovery_removals_clear_the_same_topics() -> None:
    """Removals must hit exactly the topics discovery publishes, with no payload."""
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status", instances=NAMED_MAP
    )
    removals = builder.light_discovery_removals()
    assert [p.topic for p in removals] == [p.topic for p in builder.light_discoveries()]
    assert all(p.payload == "" and p.retain for p in removals)


def test_empty_map_yields_no_lights() -> None:
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status"
    )
    assert builder.light_discoveries() == []


def test_light_state_helpers() -> None:
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status"
    )
    assert builder.light_state_topic(70) == "rvc/state/light/70"
    assert json.loads(builder.light_state_payload(125.0)) == {"brightness": 125.0}


def test_thermostat_zone_named_from_instance_map(decoder: RvcDecoder) -> None:
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status", instances=NAMED_MAP
    )
    payload = json.loads(builder.build(decode(decoder, THERMOSTAT_FRAME)).payload)
    assert payload["device"]["name"] == "Front AC"
    assert payload["device"]["suggested_area"] == "Living Room"


def test_ambient_temp_shares_the_thermostat_zone_names(decoder: RvcDecoder) -> None:
    """THERMOSTAT_AMBIENT_STATUS is the same zone, so it takes the same name."""
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status", instances=NAMED_MAP
    )
    publish = builder.build(decode(decoder, AMBIENT_FRAME))
    assert publish is not None
    payload = json.loads(publish.payload)
    assert payload["device"]["name"] == "Front AC"
    assert payload["device"]["suggested_area"] == "Living Room"


def test_unit_and_device_class_mapping(decoder: RvcDecoder) -> None:
    builder = DiscoveryBuilder(coach_id="x", availability_topic="rvc/bridge/status")
    dc_source = decoder.decode(
        make_can_id(0x1FFFD, 0x80), bytes.fromhex("0178080100943577")
    )
    publish = builder.build(dc_source)
    assert publish is not None
    components = json.loads(publish.payload)["components"]
    voltage = components["dc_voltage"]
    assert voltage["unit_of_measurement"] == "V"
    assert voltage["device_class"] == "voltage"
    # labeled fields render the label, not the raw number
    assert components["device_priority"]["value_template"] == (
        "{{ value_json.device_priority_label }}"
    )


def test_unique_ids_stable_across_builders(decoder: RvcDecoder) -> None:
    """unique_id churn would duplicate every entity in HA — must be pure."""
    message = decode(decoder, TANK_FRAME)
    one = DiscoveryBuilder("refcoach", "rvc/bridge/status").build(message)
    two = DiscoveryBuilder("refcoach", "rvc/bridge/status").build(message)
    assert one is not None and two is not None
    assert one.payload == two.payload
    assert one.topic == two.topic


def test_command_dgns_not_discovered(
    decoder: RvcDecoder, builder: DiscoveryBuilder
) -> None:
    assert builder.build(decode(decoder, COMMAND_FRAME)) is None


def test_unknown_dgn_not_discovered(
    decoder: RvcDecoder, builder: DiscoveryBuilder
) -> None:
    unknown = decoder.decode(make_can_id(0x0300F, 0x80), b"\xde\xad")
    assert builder.build(unknown) is None


RGB_MAP = InstanceMap.from_dict(
    {
        "rgb_fixtures": {
            "lounge_accent": {
                "name": "Accent",
                "area": "Living Room",
                "command_instance": 77,
                "channels": [78, 79, 80],
            }
        }
    }
)


def test_rgb_fixture_is_one_json_light_entity() -> None:
    """Four instances collapse into a single HA entity, not four."""
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status", instances=RGB_MAP
    )
    pubs = builder.rgb_discoveries()
    assert len(pubs) == 1
    assert pubs[0].topic == "homeassistant/device/rvc_refcoach_rgb_77/config"
    payload = json.loads(pubs[0].payload)
    assert payload["device"]["name"] == "Accent"
    assert payload["device"]["suggested_area"] == "Living Room"
    light = payload["components"]["light"]
    assert light["schema"] == "json"
    assert light["supported_color_modes"] == ["rgb"]
    assert light["brightness"] is True
    assert light["name"] is None
    assert light["state_topic"] == "rvc/state/rgb/77"
    assert light["command_topic"] == "rvc/cmd/rgb/77"


def test_rgb_state_payload_scales_rvc_levels_to_ha() -> None:
    """Decoded percent tops out at 125 (raw 250) for full on; HA wants 0-255."""
    builder = DiscoveryBuilder(
        coach_id="refcoach", availability_topic="rvc/bridge/status"
    )
    payload = json.loads(builder.rgb_state_payload(125.0, (125.0, 0.0, 62.5)))
    assert payload["state"] == "ON"
    assert payload["brightness"] == 255
    assert payload["color"] == {"r": 255, "g": 0, "b": 128}
    off = json.loads(builder.rgb_state_payload(0.0, (125.0, 0.0, 0.0)))
    # Colour is retained while off, so HA restores it on the next turn-on.
    assert off["state"] == "OFF"
    assert off["color"]["r"] == 255
