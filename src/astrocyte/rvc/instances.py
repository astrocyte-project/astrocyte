"""Coach RV-C instance → device map (issue #122).

The vendored spec decodes *what* a frame is (a dimmer, a thermostat); it can't
know *which* physical fixture a given instance drives — that is coach wiring,
recovered by correlating a candump against narrated toggles. This module loads
that per-coach map (`deploy/coach/config/rvc-instances.yml`) so the bridge can
publish friendly, area-placed Home Assistant entities.

**Lights are keyed on their `DC_DIMMER_COMMAND_2` instance.** The 2026-07-23
on-bus session established that this coach's `DC_DIMMER_STATUS_1` broadcasts a
fixed configuration pattern and never reflects live light state, so it cannot
source HA light entities (see ADR-012). `DC_DIMMER_COMMAND_2` is the real signal:
the wall switches broadcast it on every toggle, it carries the level, and its
instances are the ones the coach acts on. So the bridge builds each light from a
`command_instance`, tracks state from observed command traffic, and controls via
the same instance — no second instance space, no translation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_VERSION = 1

#: A colour fixture is exactly red, green, blue.
_RGB_CHANNELS = 3

#: DGN name (family) -> appliance key in the map's ``appliances`` section.
_APPLIANCE_KEYS = {"WATERHEATER_STATUS": "waterheater"}


@dataclass(frozen=True)
class EntityNaming:
    """A friendly name and optional HA area for one discovered entity."""

    name: str
    area: str | None = None


@dataclass(frozen=True)
class RgbFixture:
    """A colour fixture: one switch instance plus an R/G/B channel triplet.

    Firefly wires these as four consecutive `DC_DIMMER_COMMAND_2` instances —
    the switch the wall panel broadcasts, immediately followed by the three
    colour channels it drives. On/off and brightness go to the switch, exactly
    like a plain fixture; colour is three further commands, one per channel.
    """

    slug: str
    name: str
    area: str | None
    command_instance: int
    channels: tuple[int, int, int]


@dataclass(frozen=True)
class LightEntry:
    """One dimmable fixture, keyed on its DC_DIMMER_COMMAND_2 instance."""

    slug: str
    name: str
    area: str | None
    command_instance: int


class InstanceMap:
    """Loaded coach instance map, indexed for the bridge's lookups."""

    def __init__(
        self,
        lights: list[LightEntry] | None = None,
        thermostat_zones: dict[int, EntityNaming] | None = None,
        appliances: dict[str, dict[int, EntityNaming]] | None = None,
        rgb_fixtures: list[RgbFixture] | None = None,
    ) -> None:
        self.lights = lights or []
        self.thermostat_zones = thermostat_zones or {}
        self.appliances = appliances or {}
        self.rgb_fixtures = rgb_fixtures or []
        self._by_command = {e.command_instance: e for e in self.lights}
        self._rgb_by_switch = {f.command_instance: f for f in self.rgb_fixtures}
        #: channel instance -> (fixture, index into `channels`)
        self._rgb_by_channel: dict[int, tuple[RgbFixture, int]] = {
            channel: (fixture, index)
            for fixture in self.rgb_fixtures
            for index, channel in enumerate(fixture.channels)
        }

    @classmethod
    def empty(cls) -> InstanceMap:
        """A map that names nothing — the safe default when no file is set."""
        return cls()

    @classmethod
    def from_file(cls, path: Path | str) -> InstanceMap:
        with Path(path).open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            msg = f"instance map must be a mapping: {path}"
            raise ValueError(msg)
        version = int(data.get("version", 0))
        if version != SUPPORTED_VERSION:
            msg = (
                f"unsupported instance-map version {version} "
                f"(expected {SUPPORTED_VERSION})"
            )
            raise ValueError(msg)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstanceMap:
        lights = [
            LightEntry(
                slug=slug,
                name=str(body.get("name", slug)),
                area=_opt_str(body.get("area")),
                command_instance=int(body["command_instance"]),
            )
            for slug, body in (data.get("lights") or {}).items()
            if isinstance(body, dict)
            and _opt_int(body.get("command_instance")) is not None
        ]

        zones: dict[int, EntityNaming] = {}
        for section in ("ac_zones", "heat_zones"):
            for instance, body in (data.get(section) or {}).items():
                if isinstance(body, dict):
                    zones[int(instance)] = EntityNaming(
                        name=str(body.get("name", instance)),
                        area=_opt_str(body.get("area")),
                    )

        appliances: dict[str, dict[int, EntityNaming]] = {}
        for key, entries in (data.get("appliances") or {}).items():
            appliances[str(key)] = {
                int(instance): EntityNaming(
                    name=str(body.get("name", instance)),
                    area=_opt_str(body.get("area")),
                )
                for instance, body in (entries or {}).items()
                if isinstance(body, dict)
            }

        rgb_fixtures = []
        for slug, body in (data.get("rgb_fixtures") or {}).items():
            if not isinstance(body, dict):
                continue
            switch = _opt_int(body.get("command_instance"))
            channels = body.get("channels") or []
            # Unmapped scaffold entries carry no switch or an empty channel
            # list; skip them rather than publishing a half-defined fixture.
            if switch is None or len(channels) != _RGB_CHANNELS:
                continue
            rgb_fixtures.append(
                RgbFixture(
                    slug=slug,
                    name=str(body.get("name", slug)),
                    area=_opt_str(body.get("area")),
                    command_instance=switch,
                    channels=(
                        int(channels[0]),
                        int(channels[1]),
                        int(channels[2]),
                    ),
                )
            )

        return cls(
            lights=lights,
            thermostat_zones=zones,
            appliances=appliances,
            rgb_fixtures=rgb_fixtures,
        )

    # --- lookups the bridge/discovery use -----------------------------------

    def light_by_command_instance(self, command_instance: int) -> LightEntry | None:
        """The mapped light for a DC_DIMMER_COMMAND_2 instance, or ``None``."""
        return self._by_command.get(command_instance)

    def rgb_by_switch_instance(self, command_instance: int) -> RgbFixture | None:
        """The colour fixture whose switch is this instance, or ``None``."""
        return self._rgb_by_switch.get(command_instance)

    def rgb_by_channel_instance(
        self, command_instance: int
    ) -> tuple[RgbFixture, int] | None:
        """The fixture and colour index a channel instance belongs to."""
        return self._rgb_by_channel.get(command_instance)

    def describe_thermostat(self, instance: int) -> EntityNaming | None:
        return self.thermostat_zones.get(instance)

    def describe_appliance(self, dgn_name: str, instance: int) -> EntityNaming | None:
        key = _APPLIANCE_KEYS.get(dgn_name)
        if key is None:
            return None
        return self.appliances.get(key, {}).get(instance)


def _opt_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None
