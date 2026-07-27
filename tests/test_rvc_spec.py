"""Spec-loader tests (ADR-012), including a full parse of the vendored table."""

from pathlib import Path

import pytest

from astrocyte.rvc import RvcSpec
from astrocyte.rvc.spec import (
    _load_spec_resource,
    _normalize_name,
    merge_spec_dicts,
    spec_key_overlap,
)


@pytest.fixture(scope="module")
def spec() -> RvcSpec:
    return RvcSpec.load_vendored()


def test_vendored_spec_fully_parses(spec: RvcSpec) -> None:
    """Guards against bad re-vendors: every DGN loads through the validator."""
    assert spec.api_version == 0
    assert len(spec) >= 200
    for definition in spec.definitions.values():
        assert definition.name
        for param in definition.parameters:
            assert param.byte_end >= param.byte_start >= 0
            assert param.type
            if param.bit_start is not None:
                assert param.bit_end is not None
                assert 0 <= param.bit_start <= param.bit_end <= 7


def test_key_dgns_present(spec: RvcSpec) -> None:
    for name, dgn in [
        ("DC_DIMMER_COMMAND_2", 0x1FEDB),
        ("DC_DIMMER_STATUS_3", 0x1FEDA),
        ("TANK_STATUS", 0x1FFB7),
        ("THERMOSTAT_STATUS_1", 0x1FFE2),
        ("DC_SOURCE_STATUS_1", 0x1FFFD),
    ]:
        definition = spec.by_name(name)
        assert definition is not None, name
        assert definition.dgn == dgn


def test_field_name_normalization(spec: RvcSpec) -> None:
    dimmer = spec.by_name("DC_DIMMER_STATUS_3")
    assert dimmer is not None
    names = {p.name for p in dimmer.parameters}
    assert "operating_status_brightness" in names
    assert "delay_duration" in names


def test_alias_resolution(spec: RvcSpec) -> None:
    alias = spec.get(0x1FFFE)  # SET_DATE_TIME_COMMAND -> alias of 1FFFF
    target = spec.get(0x1FFFF)
    assert alias is not None and target is not None
    assert alias.name == "SET_DATE_TIME_COMMAND"
    assert alias.parameters == target.parameters
    assert len(alias.parameters) > 0


def test_bit_values_canonicalized_as_binary(spec: RvcSpec) -> None:
    dimmer = spec.by_name("DC_DIMMER_STATUS_3")
    assert dimmer is not None
    lock = next(p for p in dimmer.parameters if p.name == "lock_status")
    # Upstream writes "11" meaning 0b11 for bit fields.
    assert 3 in lock.values
    assert "not supported" in lock.values[3]


def test_boolean_labels_restored(spec: RvcSpec) -> None:
    """YAML 1.1 turned on/off labels into booleans; the loader restores them."""
    labels = {
        label
        for definition in spec.definitions.values()
        for param in definition.parameters
        for label in param.values.values()
    }
    assert "on" in labels
    assert "off" in labels
    assert not any(isinstance(label, bool) for label in labels)


def test_type_typos_normalized(spec: RvcSpec) -> None:
    types = {
        param.type
        for definition in spec.definitions.values()
        for param in definition.parameters
    }
    assert "unit16" not in types  # upstream typo for uint16
    assert "byte" not in types


def test_normalize_name() -> None:
    assert _normalize_name("operating status (brightness)") == (
        "operating_status_brightness"
    )
    assert _normalize_name("delay/duration") == "delay_duration"


def test_from_file_rejects_non_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "spec.yml"
    bad.write_text("- nope\n")
    with pytest.raises(ValueError, match="mapping"):
        RvcSpec.from_file(bad)


def test_vendored_entries_default_to_data_category(spec: RvcSpec) -> None:
    tank = spec.by_name("TANK_STATUS")
    assert tank is not None
    assert tank.category == "data"


def test_supplement_protocol_pgns_loaded(spec: RvcSpec) -> None:
    """The J1939 protocol PGNs from the local supplement merge in as protocol."""
    for name, dgn in [
        ("ACKNOWLEDGMENT", 0x0E800),
        ("PGN_REQUEST", 0x0EA00),
        ("TP_DT", 0x0EB00),
        ("TP_CM", 0x0EC00),
        ("ADDRESS_CLAIMED", 0x0EE00),
    ]:
        definition = spec.get(dgn)
        assert definition is not None, name
        assert definition.name == name
        assert definition.category == "protocol"


#: DGNs the supplement deliberately overrides from the vendored table:
#: DC_DIMMER_STATUS_1 (1FFBB), reclassified `internal` because it is inert on
#: coach refcoach (issue #122), and WATERHEATER_STATUS (1FFF7), restated only to
#: correct one wrong value label. Any *other* collision is an accident to catch.
_INTENTIONAL_OVERRIDES = {"1FFBB", "1FFF7"}


def test_supplement_only_intentionally_shadows_vendored() -> None:
    """Guards against silently shadowing a vendored DGN by mistake."""
    base = _load_spec_resource("rvc-spec.yml")
    supplement = _load_spec_resource("rvc-supplement.yml")
    assert spec_key_overlap(base, supplement) == _INTENTIONAL_OVERRIDES


def test_dc_dimmer_status_1_reclassified_internal() -> None:
    """The inert STATUS_1 is suppressed so it can't source HA lights (#122)."""
    spec = RvcSpec.load_vendored()
    status1 = spec.get(0x1FFBB)
    assert status1 is not None
    assert status1.name == "DC_DIMMER_STATUS_1"
    assert status1.category == "internal"


def test_merge_spec_dicts_overlay_wins() -> None:
    base = {"API_VERSION": 0, "1ABCD": {"name": "base"}}
    overlay = {"1ABCD": {"name": "override", "category": "internal"}}
    merged = merge_spec_dicts(base, overlay)
    spec = RvcSpec.from_dict(merged)
    definition = spec.get(0x1ABCD)
    assert definition is not None
    assert definition.name == "OVERRIDE"
    assert definition.category == "internal"


def test_unknown_category_rejected() -> None:
    with pytest.raises(ValueError, match="category"):
        RvcSpec.from_dict({"1ABCD": {"name": "x", "category": "bogus"}})


def test_from_file_minimal(tmp_path: Path) -> None:
    minimal = tmp_path / "spec.yml"
    minimal.write_text(
        """
API_VERSION: 0
"1ABCD":
  name: test_dgn
  parameters:
    - byte: 0
      name: instance
    - byte: 1-2
      name: level
"""
    )
    spec = RvcSpec.from_file(minimal)
    definition = spec.get(0x1ABCD)
    assert definition is not None
    assert definition.name == "TEST_DGN"
    assert definition.parameters[0].type == "uint8"
    assert definition.parameters[1].type == "uint16"  # width inferred from span


def test_waterheater_burner_status_label_corrected() -> None:
    """`burner status` must describe the burner, not the AC element.

    The vendored table labels bit 01 "ac element is active". On coach 41crb the
    field went active on the same timestamp as `operating modes` -> combustion
    and cleared with it, and stayed off through every electric-only period, so
    it tracks the diesel burner. The wrong label invites building an
    "electric element on" indicator out of a burner field.
    """
    spec = RvcSpec.load_vendored()
    definition = spec.get(0x1FFF7)
    assert definition is not None
    burner = next(p for p in definition.parameters if p.name == "burner_status")
    assert burner.values[1] == "burner is active"


def test_waterheater_override_keeps_every_vendored_parameter() -> None:
    """The 1FFF7 override restates the body, so it must not drop a field.

    The loader replaces a colliding DGN wholesale rather than merging
    parameter-by-parameter, so a copy that silently lost a parameter would
    remove telemetry without failing anything else.
    """
    vendored = RvcSpec.from_dict(_load_spec_resource("rvc-spec.yml"))
    merged = RvcSpec.load_vendored()
    base = vendored.get(0x1FFF7)
    override = merged.get(0x1FFF7)
    assert base is not None and override is not None
    assert {p.name for p in override.parameters} == {p.name for p in base.parameters}


def test_aquahot_heat_source_promoted_to_data() -> None:
    """1FE99 carries Engine Preheat and must reach HA (was `internal`)."""
    spec = RvcSpec.load_vendored()
    definition = spec.get(0x1FE99)
    assert definition is not None
    assert definition.name == "AQUAHOT_HEAT_SOURCE_STATUS"
    assert definition.category == "data"
