"""Golden decode tests against the candump fixture (ADR-012)."""

from pathlib import Path

import pytest
from can import Message
from can.io import CanutilsLogReader

from astrocyte.rvc import DecodedMessage, RvcDecoder
from astrocyte.rvc.decoder import make_can_id, split_can_id

FIXTURE = Path(__file__).parent / "fixtures" / "rvc" / "coach-synthetic.log"


@pytest.fixture(scope="module")
def decoded() -> dict[str, DecodedMessage]:
    decoder = RvcDecoder()
    out: dict[str, DecodedMessage] = {}
    with CanutilsLogReader(FIXTURE) as reader:
        for message in reader:
            assert isinstance(message, Message)
            result = decoder.decode(message.arbitration_id, bytes(message.data))
            out[result.name] = result
    return out


def test_fixture_covers_expected_dgns(decoded: dict[str, DecodedMessage]) -> None:
    assert set(decoded) == {
        "DC_DIMMER_STATUS_3",
        "TANK_STATUS",
        "THERMOSTAT_STATUS_1",
        "DC_SOURCE_STATUS_1",
        "UNKNOWN_0300F",
    }


def test_dimmer_status(decoded: dict[str, DecodedMessage]) -> None:
    msg = decoded["DC_DIMMER_STATUS_3"]
    assert msg.instance == 12
    assert msg.source_address == 0x99
    fields = {f.name: f for f in msg.fields}
    assert fields["operating_status_brightness"].value == 60.0
    assert fields["lock_status"].label == "load is unlocked"
    assert fields["enable_status"].label == "load is enabled"
    assert fields["delay_duration"].value is None  # 0xFF sentinel


def test_tank_status(decoded: dict[str, DecodedMessage]) -> None:
    msg = decoded["TANK_STATUS"]
    fields = {f.name: f for f in msg.fields}
    assert fields["instance"].label == "fresh water"
    assert fields["relative_level"].value == 2
    assert fields["resolution"].value == 4
    assert fields["absolute_level"].value is None  # 0xFFFF sentinel


def test_thermostat_status(decoded: dict[str, DecodedMessage]) -> None:
    msg = decoded["THERMOSTAT_STATUS_1"]
    assert msg.instance == 1
    fields = {f.name: f for f in msg.fields}
    assert fields["operating_mode"].label == "cool"
    assert fields["fan_speed"].value == 50.0
    assert fields["setpoint_temp_heat"].value == 20.0
    assert fields["setpoint_temp_cool"].value == 24.0


def test_dc_source_status(decoded: dict[str, DecodedMessage]) -> None:
    msg = decoded["DC_SOURCE_STATUS_1"]
    fields = {f.name: f for f in msg.fields}
    assert fields["instance"].label == "main house battery bank"
    assert fields["device_priority"].label == "battery soc device"
    assert fields["dc_voltage"].value == 13.2
    assert fields["dc_current"].value == 0.0


def test_unknown_dgn_passthrough(decoded: dict[str, DecodedMessage]) -> None:
    msg = decoded["UNKNOWN_0300F"]
    assert not msg.known
    assert msg.fields[0].value == "deadbeef"


def test_to_payload_shape(decoded: dict[str, DecodedMessage]) -> None:
    payload = decoded["THERMOSTAT_STATUS_1"].to_payload()
    assert payload["dgn"] == "1FFE2"
    assert payload["name"] == "THERMOSTAT_STATUS_1"
    assert payload["instance"] == 1
    assert payload["operating_mode_label"] == "cool"
    assert payload["setpoint_temp_cool"] == 24.0


def test_can_id_round_trip() -> None:
    can_id = make_can_id(0x1FEDB, source_address=0x82, priority=6)
    assert split_can_id(can_id) == (6, 0x1FEDB, 0x82)


def test_short_frame_skips_out_of_range_fields() -> None:
    decoder = RvcDecoder()
    msg = decoder.decode(make_can_id(0x1FFB7, 0x80), bytes([0, 2, 4]))
    names = {f.name for f in msg.fields}
    assert "relative_level" in names
    assert "absolute_level" not in names  # bytes 3-4 missing from short frame


def test_data_dgn_has_data_category() -> None:
    decoder = RvcDecoder()
    msg = decoder.decode(make_can_id(0x1FFB7, 0x80), bytes.fromhex("000204FFFFFFFFFF"))
    assert msg.category == "data"
    assert msg.destination_address is None


def test_pdu1_protocol_pgn_resolves_via_destination_mask() -> None:
    """TP.CM (0ECFF) resolves to the destination-cleared TP_CM entry."""
    decoder = RvcDecoder()
    # Transport-protocol connection-management broadcast (dest 0xFF).
    msg = decoder.decode(make_can_id(0x0ECFF, 0x24), bytes.fromhex("20120003FF0100"))
    assert msg.name == "TP_CM"
    assert msg.category == "protocol"
    assert msg.known
    assert msg.destination_address == 0xFF
    assert msg.source_address == 0x24


def test_pdu1_request_carries_destination_address() -> None:
    decoder = RvcDecoder()
    msg = decoder.decode(make_can_id(0x0EA24, 0x80), bytes.fromhex("00EE00"))
    assert msg.name == "PGN_REQUEST"
    assert msg.category == "protocol"
    assert msg.destination_address == 0x24


def test_firefly_node_sync_classified_internal() -> None:
    """The high-volume Firefly node-sync PGNs resolve to internal, not UNKNOWN."""
    decoder = RvcDecoder()
    for dgn, base in [
        (0x16F92, "FIREFLY_NODE_SYNC_16F00"),
        (0x16392, "FIREFLY_NODE_SYNC_16300"),
        (0x16E92, "FIREFLY_NODE_SYNC_16E00"),
        (0x16F8E, "FIREFLY_NODE_SYNC_16F00"),
        (0x16C92, "FIREFLY_NODE_SYNC_16C00"),
    ]:
        msg = decoder.decode(make_can_id(dgn, 0x8E), bytes.fromhex("0102030405060708"))
        assert msg.known
        assert msg.category == "internal"
        assert msg.name == base
        assert msg.destination_address == dgn & 0xFF


def test_unknown_pdu2_dgn_stays_unknown() -> None:
    """A miss that is not a known PDU1 PGN still decodes as UNKNOWN."""
    decoder = RvcDecoder()
    msg = decoder.decode(make_can_id(0x1F0F0, 0x80), bytes.fromhex("DEADBEEF"))
    assert not msg.known
    assert msg.category == "unknown"
    assert msg.name == "UNKNOWN_1F0F0"
    assert msg.destination_address is None  # PDU2: no destination-mask retry
