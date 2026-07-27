"""Offline analysis of recorded RV-C bus traffic (``astro-rvc-analyze``).

Reverse-engineering the coach's Firefly RV-C network is a candump-and-correlate
exercise: record the bus while narrating physical actions, then mine the log.
This module is the reusable toolbox for that, working on ``candump -L`` capture
files via :class:`can.io.CanutilsLogReader`. Every subcommand is a thin shell
over a pure function that returns structured data, so the analysis is unit
tested without a live bus.

Subcommands:

- ``summarize``       — DGN histogram split by decode category and source.
- ``correlate``       — per-instance first-ON timeline for one DGN/field: the
                        "toggle a fixture, see which instance lit" method (#122).
- ``clusters``        — instances that change together within a time window
                        (RGB fixtures fire several channels at once, #122).
- ``tp``              — reassemble J1939 BAM transport-protocol multipackets.
- ``slice``           — trim a capture to a representative per-DGN fixture (#91).
- ``verify-encoder``  — check our encoder reproduces observed command frames,
                        the offline half of the TX-enable gate (#91/ADR-014).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from can import Message
from can.io import CanutilsLogReader, CanutilsLogWriter

from astrocyte.rvc.decoder import RvcDecoder, split_can_id
from astrocyte.rvc.encoder import DimmerCommand

#: One captured frame: absolute timestamp, 29-bit CAN id, payload bytes.
Frame = tuple[float, int, bytes]

# --- J1939 transport protocol (BAM) -------------------------------------------
_TP_CM_PGN = 0x0EC00
_TP_DT_PGN = 0x0EB00
_TP_BAM_CONTROL = 0x20


def read_frames(path: Path | str) -> list[Frame]:
    """Load a ``candump -L`` capture into ``(timestamp, can_id, data)`` tuples."""
    frames: list[Frame] = []
    with CanutilsLogReader(str(path)) as reader:
        for message in reader:
            if not isinstance(message, Message) or message.arbitration_id is None:
                continue  # pragma: no cover - reader yields only Messages here
            frames.append(
                (message.timestamp, message.arbitration_id, bytes(message.data))
            )
    return frames


# --- summarize ----------------------------------------------------------------


@dataclass
class SummaryReport:
    """Frame counts across a capture, sliced three ways."""

    total: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    by_kind: dict[str, int] = field(default_factory=dict)
    by_source: dict[int, int] = field(default_factory=dict)

    @property
    def unknown_kinds(self) -> list[str]:
        return sorted(k for k in self.by_kind if k.startswith("UNKNOWN_"))


def summarize(
    frames: Iterable[Frame], decoder: RvcDecoder | None = None
) -> SummaryReport:
    """Tally a capture by decode category, DGN kind, and source address."""
    decoder = decoder or RvcDecoder()
    report = SummaryReport()
    for _ts, can_id, data in frames:
        message = decoder.decode(can_id, data)
        bucket = message.category if message.known else "unknown"
        report.total += 1
        report.by_category[bucket] = report.by_category.get(bucket, 0) + 1
        report.by_kind[message.name] = report.by_kind.get(message.name, 0) + 1
        report.by_source[message.source_address] = (
            report.by_source.get(message.source_address, 0) + 1
        )
    return report


# --- correlate ----------------------------------------------------------------


@dataclass(frozen=True)
class FirstOn:
    """The first time an instance's field transitioned off→on."""

    timestamp: float
    instance: int
    value: float


def _field_value(
    decoder: RvcDecoder, can_id: int, data: bytes, dgn_name: str, field_name: str
) -> tuple[int, float] | None:
    message = decoder.decode(can_id, data)
    if message.name != dgn_name or message.instance is None:
        return None
    for f in message.fields:
        if f.name == field_name and isinstance(f.value, int | float):
            return message.instance, float(f.value)
    return None


def correlate(
    frames: Iterable[Frame],
    dgn_name: str,
    field_name: str,
    decoder: RvcDecoder | None = None,
) -> list[FirstOn]:
    """First off→on transition per instance, in timestamp order.

    This is the reconcile method from #122: toggle each fixture on and leave it,
    then read the instances back in the order they lit.
    """
    decoder = decoder or RvcDecoder()
    last: dict[int, float] = {}
    seen_on: dict[int, FirstOn] = {}
    for ts, can_id, data in frames:
        found = _field_value(decoder, can_id, data, dgn_name, field_name)
        if found is None:
            continue
        instance, value = found
        previous = last.get(instance, 0.0)
        if value > 0 and previous <= 0 and instance not in seen_on:
            seen_on[instance] = FirstOn(timestamp=ts, instance=instance, value=value)
        last[instance] = value
    return sorted(seen_on.values(), key=lambda t: t.timestamp)


# --- clusters -----------------------------------------------------------------


@dataclass
class Cluster:
    """Instances whose fields changed within one time window."""

    start: float
    instances: list[int]


def clusters(
    frames: Iterable[Frame],
    dgn_name: str,
    field_name: str,
    window: float = 0.5,
    decoder: RvcDecoder | None = None,
) -> list[Cluster]:
    """Group instances that change together (RGB fires several channels, #122)."""
    decoder = decoder or RvcDecoder()
    last: dict[int, float] = {}
    events: list[tuple[float, int]] = []
    for ts, can_id, data in frames:
        found = _field_value(decoder, can_id, data, dgn_name, field_name)
        if found is None:
            continue
        instance, value = found
        if instance not in last or last[instance] != value:
            events.append((ts, instance))
        last[instance] = value

    out: list[Cluster] = []
    for ts, instance in events:
        if out and ts - out[-1].start <= window:
            if instance not in out[-1].instances:
                out[-1].instances.append(instance)
        else:
            out.append(Cluster(start=ts, instances=[instance]))
    return out


# --- transport-protocol reassembly --------------------------------------------


@dataclass
class TpMessage:
    """A reassembled J1939 BAM multipacket message."""

    source: int
    pgn: int
    data: bytes


@dataclass
class _TpAssembly:
    pgn: int
    size: int
    packets: int
    chunks: dict[int, bytes] = field(default_factory=dict)

    def complete(self) -> bool:
        return len(self.chunks) >= self.packets

    def payload(self) -> bytes:
        joined = b"".join(self.chunks[i] for i in sorted(self.chunks))
        return joined[: self.size]


def reassemble_tp(
    frames: Iterable[Frame], source: int | None = None
) -> list[TpMessage]:
    """Reassemble BAM (broadcast) transport-protocol multipackets.

    TP.CM(BAM) announces size + packet count + carried PGN; TP.DT carries the
    sequenced 7-byte chunks. Addressed (RTS/CTS) sessions are ignored — the
    coach's high-volume multipackets seen so far are all BAM broadcasts.
    """
    pending: dict[int, _TpAssembly] = {}
    out: list[TpMessage] = []
    for _ts, can_id, data in frames:
        _priority, dgn, src = split_can_id(can_id)
        if source is not None and src != source:
            continue
        base = dgn & 0x1FF00 if ((dgn >> 8) & 0xFF) < 0xF0 else dgn
        if base == _TP_CM_PGN and len(data) >= 8 and data[0] == _TP_BAM_CONTROL:
            size = data[1] | (data[2] << 8)
            packets = data[3]
            pgn = data[5] | (data[6] << 8) | (data[7] << 16)
            pending[src] = _TpAssembly(pgn=pgn, size=size, packets=packets)
        elif base == _TP_DT_PGN and src in pending and len(data) >= 1:
            assembly = pending[src]
            assembly.chunks[data[0]] = data[1:8]
            if assembly.complete():
                out.append(
                    TpMessage(source=src, pgn=assembly.pgn, data=assembly.payload())
                )
                del pending[src]
    return out


# --- slice --------------------------------------------------------------------


def slice_frames(
    frames: Iterable[Frame],
    dgn_names: set[str],
    per_dgn: int,
    decoder: RvcDecoder | None = None,
) -> list[Frame]:
    """Keep up to ``per_dgn`` frames of each named DGN — a representative slice.

    Capping per DGN (rather than an overall head) keeps low-rate telemetry in
    the slice instead of being flooded out by chatty status frames.
    """
    decoder = decoder or RvcDecoder()
    kept: dict[str, int] = defaultdict(int)
    out: list[Frame] = []
    for frame in frames:
        _ts, can_id, data = frame
        name = decoder.decode(can_id, data).name
        if name in dgn_names and kept[name] < per_dgn:
            kept[name] += 1
            out.append(frame)
    return out


def write_frames(frames: Sequence[Frame], path: Path | str) -> None:
    """Write frames back out in ``candump -L`` format."""
    writer = CanutilsLogWriter(str(path))
    try:
        for ts, can_id, data in frames:
            writer.on_message_received(
                Message(
                    timestamp=ts,
                    arbitration_id=can_id,
                    data=data,
                    is_extended_id=True,
                )
            )
    finally:
        writer.stop()


# --- verify-encoder -----------------------------------------------------------


@dataclass(frozen=True)
class EncoderCheck:
    """One observed command frame compared against our re-encoding."""

    instance: int
    ok: bool
    detail: str


def verify_encoder(
    frames: Iterable[Frame], decoder: RvcDecoder | None = None
) -> list[EncoderCheck]:
    """Re-encode observed DC_DIMMER_COMMAND_2 frames and diff the key fields.

    The offline half of the TX-enable gate (#91/ADR-014): prove our encoder
    reproduces the coach touchscreen's own command bytes (instance, level,
    command) before we ever transmit. Fill/duration bytes and source address
    are expected to differ and are not compared.
    """
    decoder = decoder or RvcDecoder()
    definition = decoder.spec.by_name(DimmerCommand.DGN_NAME)
    if definition is None:  # pragma: no cover - vendored spec always has it
        return []
    out: list[EncoderCheck] = []
    for _ts, can_id, data in frames:
        message = decoder.decode(can_id, data)
        if message.name != DimmerCommand.DGN_NAME or message.instance is None:
            continue
        observed = {f.name: f for f in message.fields}
        level = observed["desired_level"].value
        command_raw = observed["command"].raw
        if not isinstance(level, int | float) or not isinstance(command_raw, int):
            continue
        _can_id, rebuilt = DimmerCommand(
            instance=message.instance, brightness=float(level), command=command_raw
        ).to_frame(definition)
        remade = decoder.decode(_can_id, rebuilt)
        remade_fields = {f.name: f for f in remade.fields}
        diffs = [
            name
            for name in ("instance", "desired_level", "command")
            if observed[name].raw != remade_fields[name].raw
        ]
        out.append(
            EncoderCheck(
                instance=message.instance,
                ok=not diffs,
                detail="match" if not diffs else f"differs: {', '.join(diffs)}",
            )
        )
    return out


# --- CLI ----------------------------------------------------------------------


def _format_summary(report: SummaryReport) -> str:
    lines = [f"{report.total} frames"]
    lines.append("by category:")
    for name in ("data", "protocol", "internal", "unknown"):
        if name in report.by_category:
            lines.append(f"  {name:<9} {report.by_category[name]}")
    lines.append("by kind:")
    for name, count in sorted(report.by_kind.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {count:>7}  {name}")
    lines.append("by source:")
    for src, count in sorted(report.by_source.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {count:>7}  0x{src:02X}")
    if report.unknown_kinds:
        lines.append(f"still UNKNOWN: {', '.join(report.unknown_kinds)}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astro-rvc-analyze",
        description="Offline analysis of recorded RV-C bus traffic.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summarize", help="DGN histogram by category and source.")
    p_sum.add_argument("log", type=Path)

    p_cor = sub.add_parser("correlate", help="Per-instance first-ON timeline.")
    p_cor.add_argument("log", type=Path)
    p_cor.add_argument("--dgn", default="DC_DIMMER_STATUS_1")
    p_cor.add_argument("--field", default="master_brightness")

    p_clu = sub.add_parser("clusters", help="Instances that change together.")
    p_clu.add_argument("log", type=Path)
    p_clu.add_argument("--dgn", default="DC_DIMMER_COMMAND_2")
    p_clu.add_argument("--field", default="desired_level")
    p_clu.add_argument("--window", type=float, default=0.5)

    p_tp = sub.add_parser("tp", help="Reassemble BAM transport-protocol multipackets.")
    p_tp.add_argument("log", type=Path)
    p_tp.add_argument("--src", type=lambda s: int(s, 0), default=None)

    p_sl = sub.add_parser("slice", help="Trim to a representative per-DGN fixture.")
    p_sl.add_argument("log", type=Path)
    p_sl.add_argument("--dgns", required=True, help="Comma-separated DGN names.")
    p_sl.add_argument("--max-frames", type=int, default=20, help="Cap per DGN kind.")
    p_sl.add_argument("--out", type=Path, help="Write the slice (candump -L).")

    p_ve = sub.add_parser("verify-encoder", help="Diff our encoder vs observed frames.")
    p_ve.add_argument("log", type=Path)

    return parser


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI glue
    args = _build_parser().parse_args(argv)
    frames = read_frames(args.log)

    if args.command == "summarize":
        print(_format_summary(summarize(frames)))
    elif args.command == "correlate":
        for hit in correlate(frames, args.dgn, args.field):
            print(f"  {hit.timestamp:.3f}  instance {hit.instance:>3}  = {hit.value}")
    elif args.command == "clusters":
        for group in clusters(frames, args.dgn, args.field, args.window):
            joined = ", ".join(str(i) for i in group.instances)
            print(f"  {group.start:.3f}  [{joined}]")
    elif args.command == "tp":
        for msg in reassemble_tp(frames, args.src):
            print(f"  src 0x{msg.source:02X}  pgn {msg.pgn:05X}  {msg.data.hex()}")
    elif args.command == "slice":
        names = {n.strip().upper() for n in args.dgns.split(",")}
        sliced = slice_frames(frames, names, args.max_frames)
        if args.out:
            write_frames(sliced, args.out)
            print(f"wrote {len(sliced)} frames to {args.out}")
        else:
            print(f"{len(sliced)} frames match (use --out to write)")
    elif args.command == "verify-encoder":
        checks = verify_encoder(frames)
        ok = sum(1 for c in checks if c.ok)
        for check in checks:
            print(f"  instance {check.instance:>3}  {check.detail}")
        print(f"{ok}/{len(checks)} command frames re-encode exactly")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
