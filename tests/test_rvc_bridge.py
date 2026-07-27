"""Bridge unit tests (ADR-012/ADR-014) — no CAN interface or broker needed.

The safety-critical case lives here: listen-only mode must never produce a
transmittable frame, no matter what arrives on the command topics.
"""

import json

import pytest

from astrocyte.rvc import RvcDecoder
from astrocyte.rvc.bridge import BridgeSettings, RvcBridge
from astrocyte.rvc.decoder import make_can_id, split_can_id
from astrocyte.rvc.instances import InstanceMap

# Lights keyed on their DC_DIMMER_COMMAND_2 instance (#122).
LIGHT_MAP = InstanceMap.from_dict(
    {
        "lights": {
            "living_room_ceiling": {
                "name": "Living Room Ceiling",
                "area": "Living Room",
                "command_instance": 70,
            },
            "galley": {"name": "Galley", "command_instance": 55},
        }
    }
)

DIMMER_STATUS = (make_can_id(0x1FEDA, 0x99), bytes.fromhex("0C007800FF00FFFF"))
TANK_STATUS = (make_can_id(0x1FFB7, 0x80), bytes.fromhex("000204FFFFFFFFFF"))
UNKNOWN = (make_can_id(0x0300F, 0x80), bytes.fromhex("DEADBEEF"))
# J1939 transport-protocol connection-management — recognized but suppressed.
PROTOCOL_TP_CM = (make_can_id(0x0ECFF, 0x24), bytes.fromhex("20120003FF0100"))
# DC_DIMMER_COMMAND_2 for the ceiling (cmd inst 70) at level 0xFA (on).
CEILING_CMD = (make_can_id(0x1FEDB, 0x9B), bytes.fromhex("46FFFA00FFFFFFFF"))


def _one(frames: list) -> object | None:
    """The single frame a scalar command produces (colour commands yield 4)."""
    assert len(frames) <= 1
    return frames[0] if frames else None


def make_bridge(instances: InstanceMap | None = None, **overrides: object) -> RvcBridge:
    settings = BridgeSettings(
        coach_id="refcoach", mqtt_url="mqtt://test:1883", **overrides
    )
    bridge = RvcBridge(settings, decoder=RvcDecoder())
    if instances is not None:
        bridge.instances = instances
        bridge.discovery.instances = instances
    return bridge


# --- CAN -> MQTT --------------------------------------------------------------


def test_frame_publishes_discovery_then_state() -> None:
    bridge = make_bridge()
    publishes = bridge.handle_frame(*TANK_STATUS)
    topics = [p.topic for p in publishes]
    assert topics == [
        "homeassistant/device/rvc_refcoach_tank_status_0/config",
        "rvc/state/tank_status/0",
    ]
    assert all(p.retain for p in publishes)
    state = json.loads(publishes[1].payload)
    assert state["name"] == "TANK_STATUS"
    assert state["instance_label"] == "fresh water"


def test_discovery_only_published_once_per_device() -> None:
    bridge = make_bridge()
    first = bridge.handle_frame(*TANK_STATUS)
    second = bridge.handle_frame(*TANK_STATUS)
    assert len(first) == 2
    assert [p.topic for p in second] == ["rvc/state/tank_status/0"]


def test_unknown_dgn_publishes_nothing_by_default() -> None:
    bridge = make_bridge()
    assert bridge.handle_frame(*UNKNOWN) == []


def test_publish_raw_flag() -> None:
    bridge = make_bridge(publish_raw=True)
    publishes = bridge.handle_frame(*UNKNOWN)
    assert [p.topic for p in publishes] == ["rvc/raw/0300F"]
    assert publishes[0].payload == "deadbeef"


def test_protocol_frame_recognized_but_not_published() -> None:
    bridge = make_bridge()
    assert bridge.handle_frame(*PROTOCOL_TP_CM) == []
    assert bridge.decode_counts["protocol"] == 1
    assert bridge.decode_counts["data"] == 0


def test_protocol_frame_surfaces_under_publish_raw() -> None:
    bridge = make_bridge(publish_raw=True)
    publishes = bridge.handle_frame(*PROTOCOL_TP_CM)
    assert [p.topic for p in publishes] == ["rvc/raw/0ECFF"]


def test_decode_counts_tally_by_category() -> None:
    bridge = make_bridge()
    bridge.handle_frame(*TANK_STATUS)
    bridge.handle_frame(*DIMMER_STATUS)
    bridge.handle_frame(*PROTOCOL_TP_CM)
    bridge.handle_frame(*UNKNOWN)
    assert bridge.decode_counts == {
        "data": 2,
        "protocol": 1,
        "internal": 0,
        "unknown": 1,
    }
    assert bridge.total_frames == 4
    assert "data=2" in bridge.decode_summary()


def test_ha_birth_republishes_discoveries() -> None:
    bridge = make_bridge()
    bridge.handle_frame(*TANK_STATUS)
    bridge.handle_frame(*DIMMER_STATUS)
    republished = bridge.handle_ha_status("online")
    assert {p.topic for p in republished} == {
        "homeassistant/device/rvc_refcoach_tank_status_0/config",
        "homeassistant/device/rvc_refcoach_dc_dimmer_status_3_12/config",
    }
    assert bridge.handle_ha_status("offline") == []


# --- MQTT -> CAN (the safety boundary) -----------------------------------------


def test_listen_only_never_transmits() -> None:
    """Safety-critical: no command may become a frame while listen-only."""
    bridge = make_bridge()  # listen_only defaults to True
    assert bridge.settings.listen_only
    commands = [
        ("rvc/cmd/light/12/switch", b"ON"),
        ("rvc/cmd/light/12/brightness", b"255"),
        ("rvc/cmd/dc_dimmer_command_2/12", b'{"desired_level": 200}'),
    ]
    for topic, payload in commands:
        assert bridge.handle_command(topic, payload) == []
    assert bridge.dropped_commands == len(commands)


def test_light_switch_command_encodes_command_instance() -> None:
    bridge = make_bridge(instances=LIGHT_MAP, listen_only=False)
    frame = _one(bridge.handle_command("rvc/cmd/light/70/switch", b"ON"))
    assert frame is not None
    _, dgn, source = split_can_id(frame.arbitration_id)
    assert dgn == 0x1FEDB  # DC_DIMMER_COMMAND_2
    assert source == 0x82

    decoded = bridge.decoder.decode(frame.arbitration_id, bytes(frame.data))
    fields = {f.name: f for f in decoded.fields}
    assert decoded.instance == 70  # the command instance HA addressed
    assert fields["desired_level"].value == 100.0


def test_light_brightness_command_scales() -> None:
    bridge = make_bridge(instances=LIGHT_MAP, listen_only=False)
    frame = _one(bridge.handle_command("rvc/cmd/light/55/brightness", b"128"))
    assert frame is not None
    decoded = bridge.decoder.decode(frame.arbitration_id, bytes(frame.data))
    fields = {f.name: f for f in decoded.fields}
    assert decoded.instance == 55
    value = fields["desired_level"].value
    assert isinstance(value, float)
    assert value == pytest.approx(50.2, abs=0.3)


def test_unmapped_light_command_dropped_even_when_transmitting() -> None:
    """A fixture not in the coach map must never be transmitted."""
    bridge = make_bridge(instances=LIGHT_MAP, listen_only=False)
    assert bridge.handle_command("rvc/cmd/light/99/switch", b"ON") == []


def test_light_command_dropped_without_instance_map() -> None:
    bridge = make_bridge(listen_only=False)  # empty map
    assert bridge.handle_command("rvc/cmd/light/70/switch", b"ON") == []


# --- command-instance light state + discovery ---------------------------------


def test_observed_command_publishes_light_state() -> None:
    bridge = make_bridge(instances=LIGHT_MAP)
    publishes = bridge.handle_frame(*CEILING_CMD)
    assert [(p.topic, p.payload) for p in publishes] == [
        ("rvc/state/light/70", '{"brightness": 125.0}')
    ]


def test_command_for_unmapped_light_publishes_nothing() -> None:
    bridge = make_bridge(instances=LIGHT_MAP)
    # DC_DIMMER_COMMAND_2 for instance 99 (not in the map)
    assert (
        bridge.handle_frame(make_can_id(0x1FEDB, 0x9B), bytes.fromhex("63FFFA00FF"))
        == []
    )


def test_startup_publishes_light_discovery() -> None:
    bridge = make_bridge(instances=LIGHT_MAP)
    topics = {p.topic for p in bridge.startup_publishes()}
    assert topics == {
        "homeassistant/device/rvc_refcoach_light_70/config",
        "homeassistant/device/rvc_refcoach_light_55/config",
    }


def test_ha_birth_includes_map_lights() -> None:
    bridge = make_bridge(instances=LIGHT_MAP)
    bridge.handle_frame(*TANK_STATUS)
    topics = {p.topic for p in bridge.handle_ha_status("online")}
    assert "homeassistant/device/rvc_refcoach_light_70/config" in topics
    assert "homeassistant/device/rvc_refcoach_tank_status_0/config" in topics


def test_generic_json_command() -> None:
    bridge = make_bridge(listen_only=False)
    frame = _one(
        bridge.handle_command(
            "rvc/cmd/dc_dimmer_command_2/12", b'{"desired_level": 150, "command": 0}'
        )
    )
    assert frame is not None
    decoded = bridge.decoder.decode(frame.arbitration_id, bytes(frame.data))
    fields = {f.name: f for f in decoded.fields}
    assert decoded.instance == 12
    assert fields["desired_level"].value == 75.0
    assert fields["command"].label == "set brightness"


def test_malformed_and_unknown_commands_dropped() -> None:
    bridge = make_bridge(listen_only=False)
    assert bridge.handle_command("rvc/cmd/nope_dgn/1", b"{}") == []
    assert bridge.handle_command("rvc/cmd/dc_dimmer_command_2/1", b"not json") == []
    assert bridge.handle_command("other/cmd/light/1/switch", b"ON") == []
    assert bridge.handle_command("rvc/cmd/light/1/unsupported", b"1") == []


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


def _dimmer_frame(instance: int, level: int) -> tuple[int, bytes]:
    """A DC_DIMMER_COMMAND_2 frame from the lighting controller."""
    data = bytes([instance, 0xFF, level, 0x00, 0xFF, 0x00, 0xFF, 0xFF])
    return make_can_id(0x1FEDB, 0x9B), data


def test_rgb_state_assembles_across_switch_and_channels() -> None:
    """State comes from four separate instances, republished on each frame."""
    bridge = make_bridge(RGB_MAP)

    publishes = bridge.handle_frame(*_dimmer_frame(77, 250))
    rgb = [p for p in publishes if p.topic == "rvc/state/rgb/77"]
    assert len(rgb) == 1
    assert json.loads(rgb[0].payload)["brightness"] == 255
    # Channels are still dark until their own frames arrive.
    assert json.loads(rgb[0].payload)["color"] == {"r": 0, "g": 0, "b": 0}

    bridge.handle_frame(*_dimmer_frame(79, 250))  # green channel
    publishes = bridge.handle_frame(*_dimmer_frame(80, 125))  # blue channel
    payload = json.loads(
        next(p for p in publishes if p.topic == "rvc/state/rgb/77").payload
    )
    assert payload["color"] == {"r": 0, "g": 255, "b": 128}
    assert payload["brightness"] == 255, "switch level survives channel updates"


def test_rgb_command_emits_switch_and_channel_frames() -> None:
    """One HA colour command becomes four writes: switch + three channels."""
    bridge = make_bridge(RGB_MAP, listen_only=False)
    frames = bridge.handle_command(
        "rvc/cmd/rgb/77",
        b'{"state": "ON", "brightness": 255, "color": {"r": 255, "g": 0, "b": 128}}',
    )
    assert len(frames) == 4
    decoded = [bridge.decoder.decode(f.arbitration_id, bytes(f.data)) for f in frames]
    assert [d.instance for d in decoded] == [77, 78, 79, 80]
    levels = [
        next(f.value for f in d.fields if f.name == "desired_level") for d in decoded
    ]
    # 125% == the 250 raw level this coach's switches broadcast for full on.
    assert levels[0] == 125.0
    assert levels[1] == 125.0
    assert levels[2] == 0.0
    assert levels[3] == pytest.approx(62.5, abs=0.5)


def test_rgb_state_only_command_leaves_colour_alone() -> None:
    """Turning a fixture off must not clobber the colour HA restores later."""
    bridge = make_bridge(RGB_MAP, listen_only=False)
    frames = bridge.handle_command("rvc/cmd/rgb/77", b'{"state": "OFF"}')
    assert len(frames) == 1
    decoded = bridge.decoder.decode(frames[0].arbitration_id, bytes(frames[0].data))
    assert decoded.instance == 77
    assert next(f.value for f in decoded.fields if f.name == "desired_level") == 0.0


def test_rgb_command_ignored_while_listen_only() -> None:
    bridge = make_bridge(RGB_MAP)
    assert bridge.handle_command("rvc/cmd/rgb/77", b'{"state": "ON"}') == []
    assert bridge.dropped_commands == 1


def test_rgb_discovery_published_at_startup_and_birth() -> None:
    bridge = make_bridge(RGB_MAP)
    topics = [p.topic for p in bridge.startup_publishes()]
    assert "homeassistant/device/rvc_refcoach_rgb_77/config" in topics
    birth = [p.topic for p in bridge.handle_ha_status("online")]
    assert "homeassistant/device/rvc_refcoach_rgb_77/config" in birth
