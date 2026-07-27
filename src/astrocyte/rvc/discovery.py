"""HA MQTT device-based discovery for RV-C devices (ADR-011/ADR-012).

Each known, stateful ``(DGN, instance)`` pair seen on the bus becomes one Home
Assistant *device* whose discovery payload is published retained to
``homeassistant/device/<object_id>/config`` and re-published on HA's birth
message. ``unique_id``s are derived purely from coach id + DGN + instance +
field so they are stable across restarts and deploys — instability would
duplicate every entity in HA.

Telemetry fields map to ``sensor`` components. **Lights are built separately**
from the coach instance map (``light_discoveries``), keyed on their
DC_DIMMER_COMMAND_2 instance — this coach's DC_DIMMER_STATUS_1 is inert and can't
source light state (ADR-012, issue #122).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from astrocyte import __version__
from astrocyte.rvc.decoder import DecodedField, DecodedMessage
from astrocyte.rvc.instances import (
    EntityNaming,
    InstanceMap,
    LightEntry,
    RgbFixture,
)

#: RV-C unit -> (HA unit_of_measurement, HA device_class)
_UNIT_MAP: dict[str, tuple[str, str | None]] = {
    "v": ("V", "voltage"),
    "a": ("A", "current"),
    "deg c": ("°C", "temperature"),
    "pct": ("%", None),
    "hz": ("Hz", "frequency"),
    "rpm": ("rpm", None),
    "ah": ("Ah", None),
    "w": ("W", "power"),
    "pa": ("Pa", "pressure"),
    "kpa": ("kPa", "pressure"),
    "liter": ("L", "volume_storage"),
}

#: DGNs that share THERMOSTAT_STATUS_1's instance space, so the coach map's
#: zone names apply to them too — the ambient temperature a zone reports is the
#: same zone.
_THERMOSTAT_DGNS = frozenset({"THERMOSTAT_STATUS_1", "THERMOSTAT_AMBIENT_STATUS"})


@dataclass(frozen=True)
class MqttPublish:
    """One outbound MQTT message."""

    topic: str
    payload: str
    retain: bool = False


def _slug(name: str) -> str:
    return name.lower()


#: Full brightness as this coach reports it. The decoder yields percent (RV-C
#: packs half a percent per bit), and the wall switches broadcast raw 250 —
#: i.e. 125% — for a fixture turned fully on, so that is the top of the scale.
_FULL_SCALE_PCT = 125.0


def _to_255(level_pct: float) -> int:
    """Decoded RV-C percent -> HA's 0-255 brightness."""
    return max(0, min(255, int(round(level_pct * 255 / _FULL_SCALE_PCT))))


class DiscoveryBuilder:
    """Builds retained discovery payloads for decoded RV-C messages."""

    def __init__(
        self,
        coach_id: str,
        availability_topic: str,
        state_prefix: str = "rvc",
        instances: InstanceMap | None = None,
    ) -> None:
        self.coach_id = coach_id
        self.availability_topic = availability_topic
        self.state_prefix = state_prefix
        self.instances = instances or InstanceMap.empty()

    def _describe(self, message: DecodedMessage) -> EntityNaming | None:
        """Friendly name + HA area from the coach instance map, if mapped."""
        instance = message.instance
        if instance is None:
            return None
        if message.name in _THERMOSTAT_DGNS:
            return self.instances.describe_thermostat(instance)
        return self.instances.describe_appliance(message.name, instance)

    def object_id(self, message: DecodedMessage) -> str:
        instance = message.instance if message.instance is not None else 0
        return f"rvc_{self.coach_id}_{_slug(message.name)}_{instance}"

    def state_topic(self, message: DecodedMessage) -> str:
        instance = message.instance if message.instance is not None else 0
        return f"{self.state_prefix}/state/{_slug(message.name)}/{instance}"

    def build(self, message: DecodedMessage) -> MqttPublish | None:
        """Discovery payload for a message, or ``None`` when not discoverable.

        Only ``data``-category telemetry is discoverable; unknown DGNs,
        J1939 protocol/Firefly-internal frames, and command DGNs (bus echo of
        writes) produce nothing.
        """
        if message.category != "data" or "COMMAND" in message.name:
            return None
        naming = self._describe(message)
        components = self._sensor_components(message)
        if not components:
            return None

        object_id = self.object_id(message)
        instance = message.instance if message.instance is not None else 0
        default_name = f"RV-C {message.name.replace('_', ' ').title()} {instance}"
        device: dict[str, str | list[str]] = {
            "identifiers": [object_id],
            "name": naming.name if naming is not None else default_name,
            "manufacturer": "RV-C",
            "via_device": f"rvc_bridge_{self.coach_id}",
        }
        if naming is not None and naming.area is not None:
            device["suggested_area"] = naming.area
        payload = {
            "device": device,
            "origin": {
                "name": "astrocyte-rvc-bridge",
                "sw_version": __version__,
                "support_url": "https://github.com/astrocyte-project/astrocyte",
            },
            "availability_topic": self.availability_topic,
            "components": components,
        }
        return MqttPublish(
            topic=f"homeassistant/device/{object_id}/config",
            payload=json.dumps(payload, sort_keys=True),
            retain=True,
        )

    def _sensor_components(self, message: DecodedMessage) -> dict[str, dict[str, str]]:
        object_id = self.object_id(message)
        state_topic = self.state_topic(message)
        components: dict[str, dict[str, str]] = {}
        for field in message.fields:
            if field.name == "instance":
                continue
            components[field.name] = self._sensor(object_id, state_topic, field)
        return components

    @staticmethod
    def _sensor(
        object_id: str, state_topic: str, field: DecodedField
    ) -> dict[str, str]:
        component: dict[str, str] = {
            "platform": "sensor",
            "unique_id": f"{object_id}_{field.name}",
            "name": field.name.replace("_", " "),
            "state_topic": state_topic,
            "value_template": (
                f"{{{{ value_json.{field.name}_label }}}}"
                if field.label is not None
                else f"{{{{ value_json.{field.name} }}}}"
            ),
        }
        unit = (field.unit or "").lower()
        mapped = _UNIT_MAP.get(unit)
        if mapped is not None and field.label is None:
            component["unit_of_measurement"] = mapped[0]
            if mapped[1] is not None:
                component["device_class"] = mapped[1]
        return component

    # --- command-instance lights (from the coach map) -----------------------

    def light_state_topic(self, command_instance: int) -> str:
        return f"{self.state_prefix}/state/light/{command_instance}"

    @staticmethod
    def light_state_payload(brightness_pct: float) -> str:
        """State the bridge publishes when it observes a light's command."""
        return json.dumps({"brightness": brightness_pct}, sort_keys=True)

    def light_object_id(self, entry: LightEntry) -> str:
        return f"rvc_{self.coach_id}_light_{entry.command_instance}"

    def light_discovery(self, entry: LightEntry) -> MqttPublish:
        """Retained HA light discovery for one mapped fixture.

        Keyed on the DC_DIMMER_COMMAND_2 instance: state comes from observed
        command traffic on ``light_state_topic``, control goes back out on the
        matching ``cmd/light/<instance>`` topics.

        HA prefixes the device's area into the generated entity_id, so map names
        are area-*relative* ("Ceiling" in area "Bedroom") and yield
        ``light.bedroom_ceiling``. Note HA only assigns an entity_id at first
        registration — renaming a fixture later needs the retained config topic
        cleared first (``RvcBridge.reset_discovery``).
        """
        object_id = self.light_object_id(entry)
        state_topic = self.light_state_topic(entry.command_instance)
        cmd = f"{self.state_prefix}/cmd/light/{entry.command_instance}"
        device: dict[str, str | list[str]] = {
            "identifiers": [object_id],
            "name": entry.name,
            "manufacturer": "RV-C",
            "via_device": f"rvc_bridge_{self.coach_id}",
        }
        if entry.area is not None:
            device["suggested_area"] = entry.area
        payload = {
            "device": device,
            "origin": {
                "name": "astrocyte-rvc-bridge",
                "sw_version": __version__,
                "support_url": "https://github.com/astrocyte-project/astrocyte",
            },
            "availability_topic": self.availability_topic,
            "components": {
                "light": {
                    "platform": "light",
                    "unique_id": f"{object_id}_light",
                    # `null` (not the fixture name, not omitted) is what makes HA
                    # treat this as *the* entity of its device: the entity takes
                    # the device name verbatim. Naming it explicitly renders
                    # "<device> <entity>" — "Living Room Ceiling Living Room
                    # Ceiling" — and omitting it falls back to the platform class
                    # ("MQTT LightEntity"). Both verified against HA 2026.6.
                    "name": None,
                    "state_topic": state_topic,
                    "state_value_template": (
                        "{% if value_json.brightness | float(0) > 0 %}"
                        "ON{% else %}OFF{% endif %}"
                    ),
                    "command_topic": f"{cmd}/switch",
                    "brightness_state_topic": state_topic,
                    "brightness_value_template": (
                        "{{ (value_json.brightness | float(0) * 2.55) "
                        "| round(0) | int }}"
                    ),
                    "brightness_command_topic": f"{cmd}/brightness",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                }
            },
        }
        return MqttPublish(
            topic=f"homeassistant/device/{object_id}/config",
            payload=json.dumps(payload, sort_keys=True),
            retain=True,
        )

    # --- RGB colour fixtures (switch + channel triplet) ---------------------

    def rgb_object_id(self, fixture: RgbFixture) -> str:
        return f"rvc_{self.coach_id}_rgb_{fixture.command_instance}"

    def rgb_state_topic(self, command_instance: int) -> str:
        return f"{self.state_prefix}/state/rgb/{command_instance}"

    @staticmethod
    def rgb_state_payload(brightness_pct: float, rgb: tuple[int, int, int]) -> str:
        """State for one colour fixture, in HA's JSON light schema.

        Brightness is the switch's level; the colour components are the three
        channel levels. All arrive as decoded percent and are scaled to the
        0-255 HA expects, with 125% (raw 250) as full scale.
        """
        return json.dumps(
            {
                "state": "ON" if brightness_pct > 0 else "OFF",
                "brightness": _to_255(brightness_pct),
                "color": {
                    "r": _to_255(rgb[0]),
                    "g": _to_255(rgb[1]),
                    "b": _to_255(rgb[2]),
                },
            },
            sort_keys=True,
        )

    def rgb_discovery(self, fixture: RgbFixture) -> MqttPublish:
        """Retained HA discovery for one colour fixture.

        One entity per fixture rather than four: HA's JSON schema carries
        on/off, brightness and colour in a single payload, so the three channel
        instances stay an implementation detail of the bridge.
        """
        object_id = self.rgb_object_id(fixture)
        state_topic = self.rgb_state_topic(fixture.command_instance)
        device: dict[str, str | list[str]] = {
            "identifiers": [object_id],
            "name": fixture.name,
            "manufacturer": "RV-C",
            "via_device": f"rvc_bridge_{self.coach_id}",
        }
        if fixture.area is not None:
            device["suggested_area"] = fixture.area
        payload = {
            "device": device,
            "origin": {
                "name": "astrocyte-rvc-bridge",
                "sw_version": __version__,
                "support_url": "https://github.com/astrocyte-project/astrocyte",
            },
            "availability_topic": self.availability_topic,
            "components": {
                "light": {
                    "platform": "light",
                    "schema": "json",
                    "unique_id": f"{object_id}_light",
                    "name": None,
                    "state_topic": state_topic,
                    "command_topic": (
                        f"{self.state_prefix}/cmd/rgb/{fixture.command_instance}"
                    ),
                    "brightness": True,
                    "supported_color_modes": ["rgb"],
                }
            },
        }
        return MqttPublish(
            topic=f"homeassistant/device/{object_id}/config",
            payload=json.dumps(payload, sort_keys=True),
            retain=True,
        )

    def rgb_discoveries(self) -> list[MqttPublish]:
        """Discovery for every mapped colour fixture."""
        return [self.rgb_discovery(f) for f in self.instances.rgb_fixtures]

    def rgb_discovery_removals(self) -> list[MqttPublish]:
        return [
            MqttPublish(
                topic=f"homeassistant/device/{self.rgb_object_id(f)}/config",
                payload="",
                retain=True,
            )
            for f in self.instances.rgb_fixtures
        ]

    def light_discoveries(self) -> list[MqttPublish]:
        """Discovery for every mapped light — published at startup + HA birth."""
        return [self.light_discovery(e) for e in self.instances.lights]

    def light_discovery_removals(self) -> list[MqttPublish]:
        """Empty retained payloads that retire every mapped light from HA.

        An empty payload on a discovery topic deletes the device *and* its
        entities from HA's registry. That is the only way to shed an entity_id
        HA has already assigned, so it is the first half of a rename: remove,
        then let the normal startup publish re-register the fixtures under their
        new names.
        """
        return [
            MqttPublish(
                topic=f"homeassistant/device/{self.light_object_id(entry)}/config",
                payload="",
                retain=True,
            )
            for entry in self.instances.lights
        ]
