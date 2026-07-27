"""Encoder tests (ADR-012): encode/decode round trips for the command path."""

import pytest

from astrocyte.rvc import RvcDecoder, RvcSpec
from astrocyte.rvc.decoder import split_can_id
from astrocyte.rvc.encoder import (
    DimmerCommand,
    ThermostatCommand,
    UnknownFieldError,
    encode_fields,
)


@pytest.fixture(scope="module")
def spec() -> RvcSpec:
    return RvcSpec.load_vendored()


@pytest.fixture(scope="module")
def decoder(spec: RvcSpec) -> RvcDecoder:
    return RvcDecoder(spec)


def test_dimmer_command_round_trip(spec: RvcSpec, decoder: RvcDecoder) -> None:
    definition = spec.by_name(DimmerCommand.DGN_NAME)
    assert definition is not None
    command = DimmerCommand(instance=12, brightness=75.0)
    can_id, payload = command.to_frame(definition)

    priority, dgn, source_address = split_can_id(can_id)
    assert dgn == definition.dgn
    assert source_address == 0x82

    decoded = decoder.decode(can_id, payload)
    fields = {f.name: f for f in decoded.fields}
    assert decoded.instance == 12
    assert fields["desired_level"].value == 75.0  # pct scaling round-trips
    assert fields["command"].label == "set brightness"


def test_thermostat_command_round_trip(spec: RvcSpec, decoder: RvcDecoder) -> None:
    definition = spec.by_name(ThermostatCommand.DGN_NAME)
    assert definition is not None
    command = ThermostatCommand(instance=1, setpoint_heat_c=20.0, setpoint_cool_c=24.0)
    can_id, payload = command.to_frame(definition)

    decoded = decoder.decode(can_id, payload)
    fields = {f.name: f for f in decoded.fields}
    assert decoded.instance == 1
    assert fields["setpoint_temp_heat"].value == 20.0
    assert fields["setpoint_temp_cool"].value == 24.0


def test_unset_bytes_default_to_no_change(spec: RvcSpec) -> None:
    definition = spec.by_name(DimmerCommand.DGN_NAME)
    assert definition is not None
    payload = encode_fields(definition, {"instance": 5})
    assert payload[0] == 5
    assert all(b == 0xFF for b in payload[1:])  # RV-C "no data / no change"


def test_bit_field_packing(spec: RvcSpec) -> None:
    definition = spec.by_name(DimmerCommand.DGN_NAME)
    assert definition is not None
    # interlock is bits 0-1 of byte 5; packing must not clobber other bits.
    payload = encode_fields(definition, {"instance": 1, "interlock": 0b10})
    assert payload[5] & 0b11 == 0b10
    assert payload[5] & 0b11111100 == 0b11111100  # untouched bits stay 1s


def test_unknown_field_raises(spec: RvcSpec) -> None:
    definition = spec.by_name(DimmerCommand.DGN_NAME)
    assert definition is not None
    with pytest.raises(UnknownFieldError, match="warp_drive"):
        encode_fields(definition, {"warp_drive": 1})
