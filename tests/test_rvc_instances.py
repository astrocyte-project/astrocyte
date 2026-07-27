"""Instance-map loader tests (#122) — command-instance keyed lights."""

from pathlib import Path

import pytest

from astrocyte.rvc.instances import InstanceMap

EXAMPLE_MAP = Path("deploy/coach/config/rvc-instances.example.yml")


def test_empty_map_names_nothing() -> None:
    empty = InstanceMap.empty()
    assert empty.lights == []
    assert empty.light_by_command_instance(70) is None
    assert empty.describe_thermostat(0) is None


def test_from_dict_indexes_lights_by_command_instance() -> None:
    imap = InstanceMap.from_dict(
        {
            "lights": {
                "living_room_ceiling": {
                    "name": "Living Room Ceiling",
                    "area": "Living Room",
                    "command_instance": 70,
                }
            }
        }
    )
    entry = imap.light_by_command_instance(70)
    assert entry is not None
    assert entry.name == "Living Room Ceiling"
    assert entry.area == "Living Room"
    assert entry.slug == "living_room_ceiling"


def test_light_without_command_instance_is_skipped() -> None:
    """A malformed entry with no command instance is dropped, not crashed on."""
    imap = InstanceMap.from_dict(
        {"lights": {"broken": {"name": "Broken", "command_instance": None}}}
    )
    assert imap.lights == []


def test_thermostat_and_appliance_lookup() -> None:
    imap = InstanceMap.from_dict(
        {
            "ac_zones": {0: {"name": "Front AC", "area": "Living Room"}},
            "heat_zones": {5: {"name": "Bedroom Heat", "area": "Bedroom"}},
            "appliances": {"waterheater": {1: {"name": "AquaHot", "area": "Bays"}}},
        }
    )
    assert imap.describe_thermostat(0).name == "Front AC"
    assert imap.describe_thermostat(5).name == "Bedroom Heat"  # ac + heat merged
    assert imap.describe_appliance("WATERHEATER_STATUS", 1).name == "AquaHot"
    assert imap.describe_appliance("WATERHEATER_STATUS", 2) is None
    assert imap.describe_appliance("TANK_STATUS", 1) is None  # not an appliance DGN


def test_from_file_rejects_unsupported_version(tmp_path: Path) -> None:
    bad = tmp_path / "map.yml"
    bad.write_text("version: 99\nlights: {}\n")
    with pytest.raises(ValueError, match="version"):
        InstanceMap.from_file(bad)


def test_shipped_example_map_loads() -> None:
    """The example map parses and demonstrates every supported section.

    It is the schema reference and the stack's fallback mount, so a broken
    example breaks a fresh deployment. Real per-coach maps live with the
    deployment's inventory, not in this repo.
    """
    imap = InstanceMap.from_file(EXAMPLE_MAP)
    assert len(imap.lights) == 3
    assert imap.light_by_command_instance(70).name == "Ceiling"
    assert imap.light_by_command_instance(70).area == "Living Room"
    # Area + name must be unique per fixture, or HA collides entity_ids.
    assert len({(light.area, light.name) for light in imap.lights}) == len(imap.lights)
    # One complete colour fixture; the placeholder entry is skipped.
    assert len(imap.rgb_fixtures) == 1
    assert imap.rgb_by_switch_instance(77).channels == (78, 79, 80)
    assert imap.describe_thermostat(0) is not None
    assert imap.describe_appliance("WATERHEATER_STATUS", 1) is not None


def test_rgb_fixture_parsed_with_switch_and_channels() -> None:
    """A colour fixture is a switch instance plus exactly three channels."""
    imap = InstanceMap.from_dict(
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
    assert len(imap.rgb_fixtures) == 1
    fixture = imap.rgb_by_switch_instance(77)
    assert fixture is not None
    assert fixture.channels == (78, 79, 80)
    assert imap.rgb_by_channel_instance(79) == (fixture, 1)
    assert imap.rgb_by_channel_instance(77) is None  # the switch is not a channel
    assert imap.rgb_by_switch_instance(99) is None


def test_unmapped_rgb_scaffold_is_skipped() -> None:
    """Entries still awaiting an on-bus pass must not publish half a fixture."""
    imap = InstanceMap.from_dict(
        {
            "rgb_fixtures": {
                "no_channels": {"name": "TBD", "command_instance": 77, "channels": []},
                "no_switch": {"name": "TBD", "channels": [78, 79, 80]},
                "wrong_count": {
                    "name": "TBD",
                    "command_instance": 81,
                    "channels": [82, 83],
                },
            }
        }
    )
    assert imap.rgb_fixtures == []
