"""The RV-C SocketCAN↔MQTT bridge daemon (ADR-012).

Frame handling and command handling are pure functions of bridge state so
they are unit-testable without a CAN interface or broker; ``run()`` is the
thin asyncio shell wiring python-can and aiomqtt together (integration-tested
under vcan; Linux-only by design).

Safety: while ``listen_only`` is true (the default) the CAN interface is
opened in listen-only mode and :meth:`RvcBridge.handle_command` refuses to
produce frames — commands arriving on ``rvc/cmd/#`` are dropped and counted.
Enabling TX is a deliberate, post-validation config change (ADR-014 and the
install runbook).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import can
from pydantic_settings import BaseSettings, SettingsConfigDict

from astrocyte.rvc.decoder import DecodedMessage, RvcDecoder, make_can_id
from astrocyte.rvc.discovery import DiscoveryBuilder, MqttPublish
from astrocyte.rvc.encoder import DimmerCommand, encode_fields
from astrocyte.rvc.instances import InstanceMap, RgbFixture

logger = logging.getLogger(__name__)

HA_STATUS_TOPIC = "homeassistant/status"
#: Every device-based discovery config. `+` matches one whole topic level.
_DISCOVERY_TOPIC_FILTER = "homeassistant/device/+/config"
#: How long `reset_discovery` waits for the broker to replay retained configs.
_RESET_COLLECT_SECONDS = 3.0
HA_BIRTH_PAYLOAD = "online"


class BridgeSettings(BaseSettings):
    """Bridge configuration (``ASTROCYTE_RVC_*`` environment variables)."""

    model_config = SettingsConfigDict(env_prefix="ASTROCYTE_RVC_")

    can_channel: str = "can0"
    can_interface: str = "socketcan"
    mqtt_url: str = "mqtt://localhost:1883"
    mqtt_username: str = ""
    mqtt_password: str = ""
    coach_id: str = "coach"
    listen_only: bool = True
    publish_raw: bool = False
    source_address: int = 0x82
    state_prefix: str = "rvc"
    #: Path to the coach instance map (friendly names/areas + command
    #: translation). Unset → no naming and no light-command translation.
    instance_map: Path | None = None


#: Log a decode-category summary once every this many frames (soak evidence
#: for the TX-enable gate — see the CAN-tap runbook §8 / ADR-014).
_SUMMARY_EVERY = 5000


@dataclass
class RvcBridge:
    """Decodes bus traffic to MQTT and (when enabled) encodes commands back."""

    settings: BridgeSettings
    decoder: RvcDecoder = field(default_factory=RvcDecoder)
    dropped_commands: int = 0

    def __post_init__(self) -> None:
        self.instances = (
            InstanceMap.from_file(self.settings.instance_map)
            if self.settings.instance_map is not None
            else InstanceMap.empty()
        )
        self.discovery = DiscoveryBuilder(
            coach_id=self.settings.coach_id,
            availability_topic=self.status_topic,
            state_prefix=self.settings.state_prefix,
            instances=self.instances,
        )
        self._discovered: dict[str, MqttPublish] = {}
        #: switch instance -> {"brightness": level, "rgb": [r, g, b]} in RV-C
        #: levels, accumulated from observed command traffic.
        self._rgb_state: dict[int, dict[str, Any]] = {}
        #: Frames seen per decode category — the soak-gate evidence that the
        #: bus decodes cleanly (no lingering UNKNOWN) before TX is enabled.
        self.decode_counts: dict[str, int] = {
            "data": 0,
            "protocol": 0,
            "internal": 0,
            "unknown": 0,
        }

    @property
    def total_frames(self) -> int:
        return sum(self.decode_counts.values())

    def decode_summary(self) -> str:
        """One-line tally of frames seen per decode category."""
        counts = self.decode_counts
        parts = " ".join(f"{name}={counts[name]}" for name in counts)
        return f"decoded {self.total_frames} frames: {parts}"

    @property
    def status_topic(self) -> str:
        return f"{self.settings.state_prefix}/bridge/status"

    @property
    def command_topic_filter(self) -> str:
        return f"{self.settings.state_prefix}/cmd/#"

    # --- CAN -> MQTT ---------------------------------------------------------

    def handle_frame(self, can_id: int, data: bytes) -> list[MqttPublish]:
        """Decode one frame into state (+ discovery, + raw) publishes.

        Only ``data``-category frames reach MQTT/HA. Recognized J1939
        ``protocol`` plumbing and Firefly ``internal`` node-sync are counted
        and dropped (not published, not logged as UNKNOWN); ``unknown`` frames
        are still surfaced via ``publish_raw`` for reverse-engineering.
        """
        message = self.decoder.decode(can_id, data)
        bucket = message.category if message.known else "unknown"
        self.decode_counts[bucket] = self.decode_counts.get(bucket, 0) + 1
        publishes: list[MqttPublish] = []

        if self.settings.publish_raw:
            publishes.append(
                MqttPublish(
                    topic=f"{self.settings.state_prefix}/raw/{message.dgn_hex}",
                    payload=data.hex(),
                )
            )
        if message.category != "data":
            return publishes

        # Command frames are control echoes, not telemetry. The one thing worth
        # keeping is light state: this coach's switches broadcast the command
        # a fixture responds to, which is how we track a mapped light's on/off.
        if "COMMAND" in message.name:
            light_state = self._light_state_publish(message)
            if light_state is not None:
                publishes.append(light_state)
                # This fixture is now observed, so it may become available.
                assert message.instance is not None
                publishes.append(
                    self.discovery.light_observed_publish(message.instance)
                )
            rgb_state = self._rgb_state_publish(message)
            if rgb_state is not None:
                publishes.append(rgb_state)
                assert message.instance is not None
                fixture = self._rgb_fixture_for(message.instance)
                if fixture is not None:
                    publishes.append(
                        self.discovery.rgb_observed_publish(fixture.command_instance)
                    )
            return publishes

        discovery = self._discover(message)
        if discovery is not None:
            publishes.append(discovery)
        publishes.append(
            MqttPublish(
                topic=self.discovery.state_topic(message),
                payload=json.dumps(message.to_payload(), sort_keys=True),
                retain=True,
            )
        )
        return publishes

    def _light_state_publish(self, message: DecodedMessage) -> MqttPublish | None:
        """Light state derived from an observed DC_DIMMER_COMMAND_2 frame."""
        if message.name != "DC_DIMMER_COMMAND_2" or message.instance is None:
            return None
        if self.instances.light_by_command_instance(message.instance) is None:
            return None
        level = next(
            (f.value for f in message.fields if f.name == "desired_level"), None
        )
        if not isinstance(level, int | float):
            return None
        return MqttPublish(
            topic=self.discovery.light_state_topic(message.instance),
            payload=self.discovery.light_state_payload(float(level)),
            retain=True,
        )

    def _rgb_fixture_for(self, instance: int) -> RgbFixture | None:
        """Resolve a colour fixture from a switch *or* channel instance."""
        fixture = self.instances.rgb_by_switch_instance(instance)
        if fixture is not None:
            return fixture
        found = self.instances.rgb_by_channel_instance(instance)
        return None if found is None else found[0]

    def _rgb_state_publish(self, message: DecodedMessage) -> MqttPublish | None:
        """Colour-fixture state from an observed switch or channel command.

        A fixture's state is assembled from four separate instances, so each
        frame updates one component and re-publishes the whole thing. Levels
        start at 0 because the bus carries no state broadcast to seed from —
        the same caveat as plain lights.
        """
        if message.name != "DC_DIMMER_COMMAND_2" or message.instance is None:
            return None
        index: int | None = None
        fixture = self.instances.rgb_by_switch_instance(message.instance)
        if fixture is None:
            found = self.instances.rgb_by_channel_instance(message.instance)
            if found is None:
                return None
            fixture, index = found
        level = next(
            (f.value for f in message.fields if f.name == "desired_level"), None
        )
        if not isinstance(level, int | float):
            return None

        state = self._rgb_state.setdefault(
            fixture.command_instance, {"brightness": 0.0, "rgb": [0.0, 0.0, 0.0]}
        )
        if index is None:
            state["brightness"] = float(level)
        else:
            state["rgb"][index] = float(level)
        return MqttPublish(
            topic=self.discovery.rgb_state_topic(fixture.command_instance),
            payload=self.discovery.rgb_state_payload(
                state["brightness"], tuple(state["rgb"])
            ),
            retain=True,
        )

    def _discover(self, message: DecodedMessage) -> MqttPublish | None:
        """Discovery publish the first time a (DGN, instance) is seen."""
        publish = self.discovery.build(message)
        if publish is None or publish.topic in self._discovered:
            return None
        self._discovered[publish.topic] = publish
        return publish

    def startup_publishes(self) -> list[MqttPublish]:
        """Retained publishes to emit once on connect.

        Mapped-light discovery, plus an unobserved mark for every fixture. The
        mark matters because light state topics are retained and the bus carries
        no state broadcast: without it, a level from a previous session is
        replayed on restart and is indistinguishable from a live reading, and a
        switch thrown while the bridge was down is missed for good. Each fixture
        clears its own mark the first time a command for it is observed.
        """
        return [
            *self.discovery.light_discoveries(),
            *self.discovery.rgb_discoveries(),
            *self.discovery.unobserved_publishes(),
        ]

    def handle_ha_status(self, payload: str) -> list[MqttPublish]:
        """Re-publish all discoveries when HA announces its birth."""
        if payload != HA_BIRTH_PAYLOAD:
            return []
        return [
            *self.discovery.light_discoveries(),
            *self.discovery.rgb_discoveries(),
            *self._discovered.values(),
        ]

    # --- MQTT -> CAN ---------------------------------------------------------

    def handle_command(self, topic: str, payload: bytes) -> list[can.Message]:
        """Translate one ``rvc/cmd/...`` message into CAN frames.

        A list, not a single frame: a colour fixture spans four instances, so
        one HA command becomes up to four writes. Returns empty (and never
        touches the bus) while ``listen_only``.
        """
        if self.settings.listen_only:
            self.dropped_commands += 1
            logger.warning("listen-only: dropped command on %s", topic)
            return []
        try:
            if topic.split("/")[2:3] == ["rgb"]:
                return self._encode_rgb_command(topic, payload)
            frame = self._encode_command(topic, payload)
            return [frame] if frame is not None else []
        except (ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.warning("unencodable command on %s: %s", topic, exc)
            return []

    def _encode_rgb_command(self, topic: str, payload: bytes) -> list[can.Message]:
        """`rvc/cmd/rgb/<switch>` in HA's JSON light schema -> up to 4 frames.

        On/off and brightness address the switch instance; colour addresses the
        three channel instances. A payload that carries only `state` leaves the
        channels alone, so turning a fixture off does not clobber its colour.
        """
        parts = topic.split("/")
        if len(parts) != 4 or parts[0] != self.settings.state_prefix:
            return []
        fixture = self.instances.rgb_by_switch_instance(int(parts[3]))
        if fixture is None:
            return []
        body = json.loads(payload)
        definition = self.decoder.spec.by_name(DimmerCommand.DGN_NAME)
        if definition is None:
            return []

        frames: list[can.Message] = []
        if str(body.get("state", "")).upper() == "OFF":
            level_255 = 0.0
        else:
            level_255 = float(body.get("brightness", 255))
        frames.append(
            self._dimmer_frame(definition, fixture.command_instance, level_255)
        )

        colour = body.get("color")
        if isinstance(colour, dict):
            for index, key in enumerate(("r", "g", "b")):
                if key in colour:
                    frames.append(
                        self._dimmer_frame(
                            definition,
                            fixture.channels[index],
                            float(colour[key]),
                        )
                    )
        return frames

    def _dimmer_frame(
        self, definition: Any, instance: int, level_255: float
    ) -> can.Message:
        """One DC_DIMMER_COMMAND_2 frame for a 0-255 value.

        This coach's switches broadcast 250 for full on, so 255 maps to 250 —
        `DimmerCommand` takes percent at RV-C's half-a-percent per bit, hence
        the 125% full scale.
        """
        brightness_pct = max(0.0, min(255.0, level_255)) * 125.0 / 255.0
        can_id, data = DimmerCommand(
            instance=instance,
            brightness=brightness_pct,
            source_address=self.settings.source_address,
        ).to_frame(definition)
        return can.Message(arbitration_id=can_id, data=data, is_extended_id=True)

    def _encode_command(self, topic: str, payload: bytes) -> can.Message | None:
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != self.settings.state_prefix:
            return None

        # HA-facing light topics: rvc/cmd/light/<command_instance>/{switch,brightness}
        if parts[2] == "light" and len(parts) == 5:
            command_instance = int(parts[3])
            if parts[4] == "switch":
                brightness = 100.0 if payload.decode().upper() == "ON" else 0.0
            elif parts[4] == "brightness":
                brightness = round(int(payload.decode()) / 2.55, 1)
            else:
                return None
            # Only transmit to a fixture in the coach map — never an unknown
            # instance, even one HA somehow addressed.
            if self.instances.light_by_command_instance(command_instance) is None:
                logger.warning(
                    "unmapped light command instance %d; dropping", command_instance
                )
                return None
            definition = self.decoder.spec.by_name(DimmerCommand.DGN_NAME)
            if definition is None:
                return None
            command = DimmerCommand(
                instance=command_instance,
                brightness=brightness,
                source_address=self.settings.source_address,
            )
            can_id, data = command.to_frame(definition)
            return can.Message(arbitration_id=can_id, data=data, is_extended_id=True)

        # Generic: rvc/cmd/<dgn_name>/<instance> with JSON raw fields.
        if len(parts) == 4:
            definition = self.decoder.spec.by_name(parts[2].upper())
            if definition is None:
                return None
            values = {str(k): int(v) for k, v in json.loads(payload).items()}
            values.setdefault("instance", int(parts[3]))
            data = encode_fields(definition, values)
            can_id = make_can_id(definition.dgn, self.settings.source_address)
            return can.Message(arbitration_id=can_id, data=data, is_extended_id=True)
        return None

    # --- asyncio shell --------------------------------------------------------

    def _mqtt_client_kwargs(self) -> dict[str, Any]:
        import aiomqtt

        url = urlparse(self.settings.mqtt_url)
        client_kwargs: dict[str, Any] = {
            "hostname": url.hostname or "localhost",
            "port": url.port or 1883,
            "will": aiomqtt.Will(
                topic=self.status_topic, payload="offline", retain=True
            ),
        }
        if self.settings.mqtt_username:
            client_kwargs["username"] = self.settings.mqtt_username
            client_kwargs["password"] = self.settings.mqtt_password
        return client_kwargs

    async def reset_discovery(
        self, collect_seconds: float = _RESET_COLLECT_SECONDS
    ) -> list[str]:  # pragma: no cover - needs a broker (manual deploy step)
        """Retire every entity this bridge has published to HA. Returns topics.

        HA assigns an entity_id once, at first registration, and keeps it for
        good — so renaming a fixture in the instance map, or naming a zone that
        was previously anonymous, leaves the *old* id in place forever. Clearing
        the retained discovery topic deletes the device and its entities
        outright; the next normal start re-registers everything under current
        names, which is also what a fresh deployment would produce.

        Two sources are cleared: the lights the map defines (known without
        touching the bus) and every retained ``homeassistant/device/*/config``
        whose object_id carries this coach's prefix — the sensor devices, which
        the bridge only learns by seeing them on the bus. Foreign devices and
        other coaches are left alone. MQTT only: the CAN bus is never opened.
        """
        import aiomqtt

        prefix = f"homeassistant/device/rvc_{self.settings.coach_id}_"
        topics = {
            p.topic
            for p in (
                *self.discovery.light_discovery_removals(),
                *self.discovery.rgb_discovery_removals(),
            )
        }
        async with aiomqtt.Client(**self._mqtt_client_kwargs()) as client:
            await client.subscribe(_DISCOVERY_TOPIC_FILTER)
            # Retained configs all arrive right after subscribing; give the
            # broker a bounded window to deliver them, then stop listening.
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(collect_seconds):
                    async for message in client.messages:
                        topic = str(message.topic)
                        if topic.startswith(prefix) and message.payload:
                            topics.add(topic)
            for topic in sorted(topics):
                await client.publish(topic, "", retain=True)
        logger.info("cleared %d retained discovery topics", len(topics))
        return sorted(topics)

    async def run(self) -> None:  # pragma: no cover - integration-tested (vcan)
        """Run the bridge until cancelled."""
        import aiomqtt

        bus = can.Bus(
            channel=self.settings.can_channel,
            interface=self.settings.can_interface,
            receive_own_messages=False,
        )
        reader = can.AsyncBufferedReader()
        notifier = can.Notifier(bus, [reader], loop=asyncio.get_running_loop())
        client_kwargs = self._mqtt_client_kwargs()
        try:
            async with aiomqtt.Client(**client_kwargs) as client:
                await client.publish(self.status_topic, "online", retain=True)
                await client.subscribe(self.command_topic_filter)
                await client.subscribe(HA_STATUS_TOPIC)
                for publish in self.startup_publishes():
                    await client.publish(
                        publish.topic, publish.payload, retain=publish.retain
                    )
                async with asyncio.TaskGroup() as group:
                    group.create_task(self._pump_can(reader, client))
                    group.create_task(self._pump_mqtt(client, bus))
        finally:
            notifier.stop()
            bus.shutdown()

    async def _pump_can(
        self, reader: can.AsyncBufferedReader, client: Any
    ) -> None:  # pragma: no cover - integration-tested (vcan)
        async for message in reader:
            for publish in self.handle_frame(
                message.arbitration_id, bytes(message.data)
            ):
                await client.publish(
                    publish.topic, publish.payload, retain=publish.retain
                )
            if self.total_frames % _SUMMARY_EVERY == 0:
                logger.info("%s", self.decode_summary())

    async def _pump_mqtt(
        self, client: Any, bus: can.BusABC
    ) -> None:  # pragma: no cover - integration-tested (vcan)
        async for mqtt_message in client.messages:
            topic = str(mqtt_message.topic)
            payload = (
                mqtt_message.payload
                if isinstance(mqtt_message.payload, bytes)
                else str(mqtt_message.payload or "").encode()
            )
            if topic == HA_STATUS_TOPIC:
                for publish in self.handle_ha_status(payload.decode()):
                    await client.publish(
                        publish.topic, publish.payload, retain=publish.retain
                    )
                continue
            for frame in self.handle_command(topic, payload):
                bus.send(frame)
