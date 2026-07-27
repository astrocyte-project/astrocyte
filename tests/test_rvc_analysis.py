"""Tests for the astro-rvc-analyze offline log toolbox (#123/#122/#91)."""

from pathlib import Path

import pytest

from astrocyte.rvc.analysis import (
    clusters,
    correlate,
    main,
    read_frames,
    reassemble_tp,
    slice_frames,
    summarize,
    verify_encoder,
    write_frames,
)

FIXTURE = Path(__file__).parent / "fixtures" / "rvc" / "analysis-sample.log"


@pytest.fixture(scope="module")
def frames() -> list[tuple[float, int, bytes]]:
    return read_frames(FIXTURE)


def test_read_frames_roundtrips_the_capture(
    frames: list[tuple[float, int, bytes]],
) -> None:
    assert len(frames) == 13
    ts, can_id, data = frames[0]
    assert ts == pytest.approx(1000.0)
    assert data == bytes.fromhex("46FF0000FFFFFFFF")


def test_summarize_splits_by_category(frames: list[tuple[float, int, bytes]]) -> None:
    report = summarize(frames)
    assert report.total == 13
    assert report.by_category["data"] == 9  # 8 dimmer commands + 1 tank
    assert report.by_category["protocol"] == 3  # TP.CM + 2x TP.DT
    assert report.by_category["unknown"] == 1
    assert report.by_kind["DC_DIMMER_COMMAND_2"] == 8
    assert report.unknown_kinds == ["UNKNOWN_1F0F0"]
    assert report.by_source[0x9B] == 9  # dimmer commands + the unknown


def test_correlate_recovers_first_on_order(
    frames: list[tuple[float, int, bytes]],
) -> None:
    hits = correlate(frames, "DC_DIMMER_COMMAND_2", "desired_level")
    order = [(h.instance, h.value) for h in hits]
    # instance 70 lit first, then 67, then 69 — in narrated toggle order.
    assert order[:3] == [(70, 100.0), (67, 50.0), (69, 100.0)]


def test_clusters_groups_simultaneous_channels(
    frames: list[tuple[float, int, bytes]],
) -> None:
    groups = clusters(frames, "DC_DIMMER_COMMAND_2", "desired_level", window=0.5)
    rgb = [g for g in groups if set(g.instances) == {78, 79, 80}]
    assert len(rgb) == 1  # the three channels fired together within the window


def test_reassemble_tp_recovers_bam_payload(
    frames: list[tuple[float, int, bytes]],
) -> None:
    messages = reassemble_tp(frames)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.source == 0x24
    assert msg.pgn == 0x12345
    assert msg.data == bytes.fromhex("112233445566778899")


def test_reassemble_tp_filters_by_source(
    frames: list[tuple[float, int, bytes]],
) -> None:
    assert reassemble_tp(frames, source=0x99) == []
    assert len(reassemble_tp(frames, source=0x24)) == 1


def test_slice_caps_per_dgn(frames: list[tuple[float, int, bytes]]) -> None:
    sliced = slice_frames(frames, {"DC_DIMMER_COMMAND_2", "TANK_STATUS"}, per_dgn=2)
    names_only = summarize(sliced).by_kind
    assert names_only == {"DC_DIMMER_COMMAND_2": 2, "TANK_STATUS": 1}


def test_slice_write_roundtrip(
    frames: list[tuple[float, int, bytes]], tmp_path: Path
) -> None:
    sliced = slice_frames(frames, {"TANK_STATUS"}, per_dgn=5)
    out = tmp_path / "slice.log"
    write_frames(sliced, out)
    reread = read_frames(out)
    assert len(reread) == 1
    assert reread[0][1] == sliced[0][1]  # same CAN id survives the round trip


def test_verify_encoder_matches_observed_command_frames(
    frames: list[tuple[float, int, bytes]],
) -> None:
    checks = verify_encoder(frames)
    assert len(checks) == 8  # one per DC_DIMMER_COMMAND_2 frame
    assert all(c.ok for c in checks)
    assert {c.instance for c in checks} == {70, 67, 69, 78, 79, 80}


def test_main_summarize_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["summarize", str(FIXTURE)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "13 frames" in out
    assert "DC_DIMMER_COMMAND_2" in out


def test_main_verify_encoder_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["verify-encoder", str(FIXTURE)])
    assert rc == 0
    assert "8/8 command frames re-encode exactly" in capsys.readouterr().out
