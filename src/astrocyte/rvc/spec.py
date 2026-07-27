"""Typed loader for the vendored RV-C DGN decode table (ADR-012).

The upstream YAML (``spec/rvc-spec.yml``, Apache-2.0 — see NOTICE) is a
community artifact with real-world warts this loader normalizes:

- ``alias`` entries reuse another DGN's parameter list under their own name.
- YAML 1.1 parsed unquoted ``on``/``off`` labels into booleans — restored to
  ``"on"``/``"off"`` strings here.
- ``values`` keys for ``bit*``-typed fields are binary renditions (``11`` is
  0b11 = 3); other numeric keys are decimal. Keys whose digits are all 0/1
  are interpreted as binary for bit fields, decimal otherwise.
- A handful of type typos (``unit16``) and untyped parameters — normalized to
  a sensible width from the byte/bit span.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

_TYPE_ALIASES = {
    "unit16": "uint16",
    "uint": "uint8",
    "byte": "uint8",
}


def _normalize_name(raw: str) -> str:
    """``"operating status (brightness)"`` -> ``operating_status_brightness``."""
    cleaned = [c if c.isalnum() else " " for c in raw.lower()]
    return "_".join("".join(cleaned).split())


def _parse_span(raw: int | str) -> tuple[int, int]:
    """``3`` -> (3, 3); ``"3-4"`` -> (3, 4)."""
    if isinstance(raw, int):
        return raw, raw
    start_s, _, end_s = str(raw).partition("-")
    start = int(start_s)
    return start, int(end_s) if end_s else start


def _label(value: Any) -> str:
    """Restore YAML-1.1 boolean mangling of on/off labels."""
    if value is True:
        return "on"
    if value is False:
        return "off"
    return str(value)


def _parse_values(raw: dict[Any, Any] | None, *, is_bit_type: bool) -> dict[int, str]:
    """Canonicalize a values table to ``{raw_int: label}``."""
    if not raw:
        return {}
    out: dict[int, str] = {}
    for key, value in raw.items():
        key_s = str(int(key)) if isinstance(key, bool) else str(key)
        if not key_s.lstrip("-").isdigit():
            continue  # non-numeric key: unusable for lookup
        if is_bit_type and set(key_s) <= {"0", "1"}:
            canonical = int(key_s, 2)
        else:
            canonical = int(key_s)
        out.setdefault(canonical, _label(value))
    return out


@dataclass(frozen=True)
class ParameterDef:
    """One decoded field within a DGN's 8-byte payload."""

    name: str
    byte_start: int
    byte_end: int
    bit_start: int | None = None
    bit_end: int | None = None
    type: str = "uint8"
    unit: str | None = None
    values: dict[int, str] = field(default_factory=dict)

    @property
    def is_bit_field(self) -> bool:
        return self.bit_start is not None

    @property
    def byte_length(self) -> int:
        return self.byte_end - self.byte_start + 1


#: DGN classifications understood by the loader (see ``rvc-supplement.yml``).
#: Vendored entries have no ``category`` key and default to ``"data"``.
_CATEGORIES = frozenset({"data", "protocol", "internal"})


@dataclass(frozen=True)
class DgnDefinition:
    """One DGN (17-bit RV-C data-group number) and its parameters.

    ``category`` sorts frames for the bridge: ``data`` is decoded and published;
    ``protocol`` (J1939 plumbing) and ``internal`` (Firefly node-sync chatter)
    are recognized but suppressed rather than logged as ``UNKNOWN``.
    """

    dgn: int
    name: str
    parameters: tuple[ParameterDef, ...] = ()
    category: str = "data"


def _parse_parameter(raw: dict[str, Any], index: int) -> ParameterDef:
    byte_start, byte_end = _parse_span(raw["byte"])
    bit_start: int | None = None
    bit_end: int | None = None
    if raw.get("bit") is not None:
        bit_start, bit_end = _parse_span(raw["bit"])

    raw_type = str(raw.get("type", "")).strip().lower()
    param_type = _TYPE_ALIASES.get(raw_type, raw_type)
    if not param_type:
        if bit_start is not None and bit_end is not None:
            param_type = f"bit{bit_end - bit_start + 1}"
        elif byte_end - byte_start + 1 > 1:
            param_type = f"uint{8 * (byte_end - byte_start + 1)}"
        else:
            param_type = "uint8"

    name = raw.get("name")
    normalized = _normalize_name(str(name)) if name else f"field_{index}"
    return ParameterDef(
        name=normalized,
        byte_start=byte_start,
        byte_end=byte_end,
        bit_start=bit_start,
        bit_end=bit_end,
        type=param_type,
        unit=str(raw["unit"]) if raw.get("unit") is not None else None,
        values=_parse_values(
            raw.get("values"), is_bit_type=param_type.startswith("bit")
        ),
    )


class RvcSpec:
    """The loaded decode table, indexed by DGN."""

    def __init__(self, definitions: dict[int, DgnDefinition], api_version: int) -> None:
        self.definitions = definitions
        self.api_version = api_version
        self._by_name = {d.name: d for d in definitions.values()}

    def get(self, dgn: int) -> DgnDefinition | None:
        return self.definitions.get(dgn)

    def by_name(self, name: str) -> DgnDefinition | None:
        return self._by_name.get(name)

    def __len__(self) -> int:
        return len(self.definitions)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RvcSpec:
        api_version = int(data.get("API_VERSION", 0))
        # Entries with non-hex keys (e.g. ``Z0000``) are shared parameter
        # templates for aliasing, not real DGNs.
        bodies: dict[str, tuple[str, tuple[ParameterDef, ...], str]] = {}
        aliases: list[tuple[str, str, str, str]] = []  # (key, name, target, cat)

        for key, body in data.items():
            if key == "API_VERSION" or not isinstance(body, dict):
                continue
            key_s = str(key)
            name = _normalize_name(str(body.get("name", key_s))).upper()
            category = str(body.get("category", "data")).strip().lower() or "data"
            if category not in _CATEGORIES:
                msg = f"unknown category {category!r} for DGN {key_s}"
                raise ValueError(msg)
            if "alias" in body:
                aliases.append((key_s, name, str(body["alias"]), category))
                continue
            raw_params = body.get("parameters") or []
            parameters = tuple(
                _parse_parameter(raw, i) for i, raw in enumerate(raw_params)
            )
            bodies[key_s] = (name, parameters, category)

        def _hex(key: str) -> int | None:
            try:
                return int(key, 16)
            except ValueError:
                return None

        parsed: dict[int, DgnDefinition] = {
            dgn: DgnDefinition(
                dgn=dgn, name=name, parameters=parameters, category=category
            )
            for key, (name, parameters, category) in bodies.items()
            if (dgn := _hex(key)) is not None
        }
        for key, name, target_key, category in aliases:
            dgn = _hex(key)
            if dgn is None:
                continue
            _, parameters, _ = bodies.get(target_key, (name, (), "data"))
            parsed[dgn] = DgnDefinition(
                dgn=dgn, name=name, parameters=parameters, category=category
            )

        return cls(parsed, api_version)

    @classmethod
    def from_file(cls, path: Path | str) -> RvcSpec:
        with Path(path).open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            msg = f"RV-C spec must be a mapping: {path}"
            raise ValueError(msg)
        return cls.from_dict(data)

    @classmethod
    def load_vendored(cls) -> RvcSpec:
        """Load the shipped decode table: vendored base + local supplement.

        The upstream ``rvc-spec.yml`` stays byte-identical to its vendored
        commit; our reverse-engineered additions and J1939 protocol-PGN
        classifications live in ``rvc-supplement.yml`` and are merged on top
        (the supplement wins on key collision).
        """
        base = _load_spec_resource("rvc-spec.yml")
        supplement = _load_spec_resource("rvc-supplement.yml")
        return cls.from_dict(merge_spec_dicts(base, supplement))


def _load_spec_resource(filename: str) -> dict[str, Any]:
    ref = resources.files("astrocyte.rvc") / "spec" / filename
    data = yaml.safe_load(ref.read_text(encoding="utf-8"))
    if not isinstance(data, dict):  # pragma: no cover - packaging error
        msg = f"vendored {filename} is not a mapping"
        raise ValueError(msg)
    return data


def spec_key_overlap(base: dict[str, Any], overlay: dict[str, Any]) -> set[str]:
    """DGN keys the overlay redefines from the base (``API_VERSION`` aside)."""
    return {
        key
        for key in overlay
        if key != "API_VERSION" and key in base and isinstance(overlay[key], dict)
    }


def merge_spec_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Overlay one raw spec mapping onto another; overlay wins per DGN key."""
    return {**base, **overlay}
