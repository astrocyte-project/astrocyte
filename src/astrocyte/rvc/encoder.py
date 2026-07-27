"""RV-C frame encoding — the bridge's command path (ADR-012/ADR-014).

Encoding is generic (named raw fields packed into a DGN's byte/bit layout,
unused bits left at the RV-C "no change" all-ones default) plus typed command
helpers for the coach's safe-control set. The bridge refuses to transmit any
of this while ``listen_only`` is set; policy (ADR-014) gates it above.
"""

from __future__ import annotations

from dataclasses import dataclass

from astrocyte.rvc.decoder import make_can_id
from astrocyte.rvc.spec import DgnDefinition

#: RV-C convention: unset bytes are 0xFF ("no data / no change").
_FILL = 0xFF


class UnknownFieldError(ValueError):
    """A field name not present in the DGN definition."""


def encode_fields(
    definition: DgnDefinition,
    values: dict[str, int],
    *,
    length: int = 8,
) -> bytes:
    """Pack named raw field values into a payload (inverse of decoding)."""
    data = bytearray([_FILL] * length)
    by_name = {p.name: p for p in definition.parameters}
    for name, raw in values.items():
        param = by_name.get(name)
        if param is None:
            msg = f"{definition.name} has no field {name!r}"
            raise UnknownFieldError(msg)
        span = param.byte_length
        if param.bit_start is not None and param.bit_end is not None:
            width = param.bit_end - param.bit_start + 1
            mask = ((1 << width) - 1) << param.bit_start
            current = int.from_bytes(
                data[param.byte_start : param.byte_end + 1], "little"
            )
            current = (current & ~mask) | ((raw << param.bit_start) & mask)
            data[param.byte_start : param.byte_end + 1] = current.to_bytes(
                span, "little"
            )
        else:
            data[param.byte_start : param.byte_end + 1] = raw.to_bytes(span, "little")
    return bytes(data)


@dataclass(frozen=True)
class DimmerCommand:
    """DC_DIMMER_COMMAND_2 — lights (control tier).

    ``brightness`` is percent (0-100); RV-C encodes percent at 0.5%/bit.
    """

    instance: int
    brightness: float
    command: int = 0  # 0 = "set brightness"
    source_address: int = 0x82

    DGN_NAME = "DC_DIMMER_COMMAND_2"

    def to_frame(self, definition: DgnDefinition) -> tuple[int, bytes]:
        payload = encode_fields(
            definition,
            {
                "instance": self.instance,
                "desired_level": int(round(self.brightness * 2)),
                "command": self.command,
            },
        )
        return make_can_id(definition.dgn, self.source_address), payload


@dataclass(frozen=True)
class ThermostatCommand:
    """THERMOSTAT_COMMAND_1 — HVAC setpoints (control tier).

    Temperatures are °C; RV-C encodes uint16 as ``(t + 273) / 0.03125``.
    """

    instance: int
    setpoint_heat_c: float | None = None
    setpoint_cool_c: float | None = None
    source_address: int = 0x82

    DGN_NAME = "THERMOSTAT_COMMAND_1"

    @staticmethod
    def _encode_temp(celsius: float) -> int:
        return int(round((celsius + 273) / 0.03125))

    def to_frame(self, definition: DgnDefinition) -> tuple[int, bytes]:
        values: dict[str, int] = {"instance": self.instance}
        if self.setpoint_heat_c is not None:
            values["setpoint_temp_heat"] = self._encode_temp(self.setpoint_heat_c)
        if self.setpoint_cool_c is not None:
            values["setpoint_temp_cool"] = self._encode_temp(self.setpoint_cool_c)
        payload = encode_fields(definition, values)
        return make_can_id(definition.dgn, self.source_address), payload
