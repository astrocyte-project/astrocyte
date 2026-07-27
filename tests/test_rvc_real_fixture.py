"""Golden decode + encoder validation against a real refcoach capture (#91).

Distinct from ``test_rvc_decoder.py`` (which guards the synthetic
``coach-synthetic.log`` — deliberately left untouched). This slice is trimmed
from the 2026-07-21 coach-node capture of the live Firefly bus, so it double-checks
that real coach frames decode to the values we expect, that the whole slice
classifies cleanly (no lingering UNKNOWN beyond a documented allowlist), and
that our command encoder reproduces the coach's own touchscreen frames.
"""

from pathlib import Path

import pytest

from astrocyte.rvc import DecodedMessage, RvcDecoder
from astrocyte.rvc.analysis import read_frames, verify_encoder

FIXTURE = Path(__file__).parent / "fixtures" / "rvc" / "coach-reference-20260721.log"

# The whole slice now classifies cleanly: every DGN it contains resolves to
# data/protocol/internal, with nothing left as UNKNOWN. The proprietary DGNs the
# 2026-07-21 capture surfaced (15FCE and the rest of #123) are recognized as
# `internal` — see rvc-supplement.yml.
KNOWN_UNDECODED: set[str] = set()


@pytest.fixture(scope="module")
def decoded() -> list[DecodedMessage]:
    decoder = RvcDecoder()
    return [decoder.decode(cid, data) for _ts, cid, data in read_frames(FIXTURE)]


def _first(decoded: list[DecodedMessage], name: str) -> DecodedMessage:
    return next(m for m in decoded if m.name == name)


def test_slice_decodes_cleanly(decoded: list[DecodedMessage]) -> None:
    """No frame should be UNKNOWN except the documented, still-to-decode DGN."""
    unknown = {m.name for m in decoded if not m.known}
    assert unknown <= KNOWN_UNDECODED, unknown
    categories = {m.category for m in decoded}
    assert categories <= {"data", "protocol", "internal", "unknown"}


def test_slice_covers_the_key_dgns(decoded: list[DecodedMessage]) -> None:
    names = {m.name for m in decoded}
    assert {
        "DC_DIMMER_STATUS_1",
        "DC_DIMMER_COMMAND_2",
        "THERMOSTAT_STATUS_1",
        "TANK_STATUS",
        "WATERHEATER_STATUS",
        "DC_SOURCE_STATUS_1",
        "TP_CM",
        "FIREFLY_NODE_SYNC_16F00",
    } <= names


def test_proprietary_dgns_recognized_as_internal(
    decoded: list[DecodedMessage],
) -> None:
    """The #123 proprietary broadcasts resolve to named `internal`, not UNKNOWN."""
    by_name = {m.name: m for m in decoded}
    expected = {
        "DC_DIMMER_CHANNEL_STATUS",  # 15FCE
        "DC_DIMMER_PROP_1AA00",  # 1AAFD + 1AADC via one base-keyed entry
        "DC_DIMMER_IDENT",  # 1FACF
        "PROP_B_0FF01",
        "PROP_STATUS_1FEA3",
        "PROP_IDENT_1FACE",
    }
    assert expected <= set(by_name), expected - set(by_name)
    assert all(by_name[name].category == "internal" for name in expected)


def test_base_key_covers_both_1aa00_destinations(
    decoded: list[DecodedMessage],
) -> None:
    """One 1AA00 entry covers the addressed siblings 1AAFD (0xFD) and 1AADC (0xDC)."""
    prop = [m for m in decoded if m.name == "DC_DIMMER_PROP_1AA00"]
    assert {m.destination_address for m in prop} == {0xFD, 0xDC}


def test_golden_tank_and_battery(decoded: list[DecodedMessage]) -> None:
    tank = {f.name: f for f in _first(decoded, "TANK_STATUS").fields}
    assert tank["instance"].label == "lpg"
    assert tank["relative_level"].value == 81

    source = {f.name: f for f in _first(decoded, "DC_SOURCE_STATUS_1").fields}
    assert source["instance"].label == "main house battery bank"
    assert source["dc_voltage"].value == pytest.approx(13.45, abs=0.01)


def test_golden_thermostat_and_waterheater(decoded: list[DecodedMessage]) -> None:
    thermo = _first(decoded, "THERMOSTAT_STATUS_1")
    assert thermo.instance == 0  # front zone
    assert {f.name: f for f in thermo.fields}["operating_mode"].label == "cool"

    heater = {f.name: f for f in _first(decoded, "WATERHEATER_STATUS").fields}
    assert heater["water_temperature"].value == pytest.approx(29.8, abs=0.1)


def test_encoder_reproduces_observed_command_frames(
    decoded: list[DecodedMessage],
) -> None:
    """Every observed DC_DIMMER_COMMAND_2 frame must re-encode byte-exact (#91)."""
    checks = verify_encoder(read_frames(FIXTURE))
    assert checks  # the slice contains command frames
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]
