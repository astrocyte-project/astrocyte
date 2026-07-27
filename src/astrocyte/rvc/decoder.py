"""RV-C frame decoding (ADR-012).

A 29-bit RV-C CAN identifier packs ``priority (3) | DGN (17) | source
address (8)``. The payload layout per DGN comes from the vendored spec table
(``spec.py``); this module extracts raw field values and applies the standard
RV-C unit scalings:

===========  =======  ====================================
unit         type     engineering value
===========  =======  ====================================
pct          uint8    raw / 2 (255 = unavailable)
deg c        uint8    raw - 40 (255 = unavailable)
deg c        uint16   raw * 0.03125 - 273 (65535 = n/a)
v            uint16   raw * 0.05 (65535 = unavailable)
a            uint16   raw * 0.05 - 1600 (65535 = n/a)
a            uint32   raw * 0.001 - 2000000 (2^32-1 = n/a)
hz           uint16   raw / 128
bitmap       uint8    zero-padded binary string
===========  =======  ====================================

Anything else passes through raw. All-ones raw values in sized uints decode
to ``None`` (RV-C "data not available").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from astrocyte.rvc.spec import DgnDefinition, ParameterDef, RvcSpec

_UNAVAILABLE = {1: 0xFF, 2: 0xFFFF, 4: 0xFFFFFFFF}


def split_can_id(can_id: int) -> tuple[int, int, int]:
    """Return ``(priority, dgn, source_address)`` from a 29-bit identifier."""
    return (can_id >> 26) & 0x7, (can_id >> 8) & 0x1FFFF, can_id & 0xFF


def _is_pdu1(dgn: int) -> bool:
    """True for J1939 PDU1 (addressed) DGNs — PDU Format byte below 0xF0."""
    return ((dgn >> 8) & 0xFF) < 0xF0


def make_can_id(dgn: int, source_address: int, priority: int = 6) -> int:
    """Build a 29-bit RV-C identifier."""
    return ((priority & 0x7) << 26) | ((dgn & 0x1FFFF) << 8) | (source_address & 0xFF)


@dataclass(frozen=True)
class DecodedField:
    name: str
    raw: int | str
    value: float | int | str | None
    unit: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class DecodedMessage:
    dgn: int
    name: str
    priority: int
    source_address: int
    fields: tuple[DecodedField, ...]
    known: bool = True
    #: ``data`` | ``protocol`` | ``internal`` | ``unknown`` (see ``spec.py``).
    #: Only ``data`` frames are published to MQTT / discovered in HA.
    category: str = "data"
    #: Destination address for PDU1 (J1939 addressed) frames, else ``None``.
    destination_address: int | None = None

    @property
    def dgn_hex(self) -> str:
        return f"{self.dgn:05X}"

    @property
    def instance(self) -> int | None:
        """The instance field, if this DGN carries one."""
        for f in self.fields:
            if f.name == "instance" and isinstance(f.raw, int):
                return f.raw
        return None

    def to_payload(self) -> dict[str, Any]:
        """JSON-ready payload for the MQTT spine (``rvc/state/...``)."""
        payload: dict[str, Any] = {
            "dgn": self.dgn_hex,
            "name": self.name,
            "source_address": self.source_address,
        }
        if self.instance is not None:
            payload["instance"] = self.instance
        for f in self.fields:
            payload[f.name] = f.value
            if f.label is not None:
                payload[f"{f.name}_label"] = f.label
        return payload


def _extract_raw(data: bytes, param: ParameterDef) -> int:
    """Little-endian byte span, then optional bit slice."""
    span = data[param.byte_start : param.byte_end + 1]
    raw = int.from_bytes(span, "little")
    if param.bit_start is not None and param.bit_end is not None:
        width = param.bit_end - param.bit_start + 1
        raw = (raw >> param.bit_start) & ((1 << width) - 1)
    return raw


def _scale(raw: int, param: ParameterDef) -> float | int | str | None:
    if not param.is_bit_field:
        sentinel = _UNAVAILABLE.get(param.byte_length)
        if sentinel is not None and raw == sentinel:
            return None
    unit = (param.unit or "").lower()
    if unit == "pct":
        return raw / 2
    if unit == "deg c":
        if param.byte_length >= 2:
            return round(raw * 0.03125 - 273, 3)
        return raw - 40
    if unit == "v" and param.byte_length >= 2:
        return round(raw * 0.05, 3)
    if unit == "a":
        if param.byte_length >= 4:
            return round(raw * 0.001 - 2_000_000, 3)
        if param.byte_length == 2:
            return round(raw * 0.05 - 1600, 3)
        return raw
    if unit == "hz" and param.byte_length >= 2:
        return round(raw / 128, 3)
    if unit == "bitmap":
        return f"{raw:08b}"
    return raw


class RvcDecoder:
    """Decodes raw CAN frames using a loaded :class:`RvcSpec`."""

    def __init__(self, spec: RvcSpec | None = None) -> None:
        self.spec = spec if spec is not None else RvcSpec.load_vendored()

    def decode(self, can_id: int, data: bytes) -> DecodedMessage:
        priority, dgn, source_address = split_can_id(can_id)
        definition = self.spec.get(dgn)
        destination_address: int | None = None
        if definition is None and _is_pdu1(dgn):
            # PDU1 (J1939 addressed): the low DGN byte is the destination
            # address, not part of the PGN. Look up the destination-cleared
            # PGN so one spec entry covers every destination.
            destination_address = dgn & 0xFF
            definition = self.spec.get(dgn & 0x1FF00)
        if definition is None:
            return DecodedMessage(
                dgn=dgn,
                name=f"UNKNOWN_{dgn:05X}",
                priority=priority,
                source_address=source_address,
                fields=(DecodedField(name="data", raw=data.hex(), value=data.hex()),),
                known=False,
                category="unknown",
                destination_address=destination_address,
            )
        return DecodedMessage(
            dgn=dgn,
            name=definition.name,
            priority=priority,
            source_address=source_address,
            fields=self._decode_fields(definition, data),
            category=definition.category,
            destination_address=destination_address,
        )

    @staticmethod
    def _decode_fields(
        definition: DgnDefinition, data: bytes
    ) -> tuple[DecodedField, ...]:
        fields: list[DecodedField] = []
        for param in definition.parameters:
            if param.byte_end >= len(data):
                continue  # short frame: skip fields beyond the payload
            if param.type == "ascii":
                text = (
                    data[param.byte_start : param.byte_end + 1]
                    .rstrip(b"\xff\x00")
                    .decode("ascii", errors="replace")
                )
                fields.append(DecodedField(name=param.name, raw=text, value=text))
                continue
            raw = _extract_raw(data, param)
            fields.append(
                DecodedField(
                    name=param.name,
                    raw=raw,
                    value=_scale(raw, param),
                    unit=param.unit,
                    label=param.values.get(raw),
                )
            )
        return tuple(fields)
