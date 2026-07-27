"""CLI tests: `aios approve` against a mocked API (ADR-014)."""

import json
from collections.abc import Iterator

import httpx
import pytest

from astrocyte.cli import main as cli


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[httpx.Request]]:
    """Route the CLI's HTTP calls to a canned in-process API."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/approvals":
            return httpx.Response(
                200,
                json=[
                    {
                        "approval_id": "abc123",
                        "domain": "water_heater",
                        "service": "turn_on",
                        "targets": ["wh.main"],
                        "status": "pending",
                        "expires_at": 0,
                    }
                ],
            )
        if request.method == "POST" and request.url.path == "/v1/approvals/abc123":
            body = json.loads(request.content)
            status = "approved" if body["approve"] else "denied"
            return httpx.Response(
                200,
                json={
                    "approval_id": "abc123",
                    "domain": "water_heater",
                    "service": "turn_on",
                    "targets": ["wh.main"],
                    "status": status,
                    "expires_at": 0,
                },
            )
        return httpx.Response(404, json={"detail": "unknown approval"})

    def client_factory() -> httpx.Client:
        return httpx.Client(
            base_url="http://testserver", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(cli, "_api_client", client_factory)
    yield requests


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "aios" in capsys.readouterr().out


def test_no_command_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    assert "usage: aios" in capsys.readouterr().out


def test_approve_lists_pending(
    api: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["approve"]) == 0
    out = capsys.readouterr().out
    assert "abc123" in out
    assert "water_heater.turn_on" in out


def test_approve_resolves(
    api: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["approve", "abc123"]) == 0
    assert "approved" in capsys.readouterr().out
    body = json.loads(api[-1].content)
    assert body == {"approve": True}


def test_approve_deny_flag(
    api: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["approve", "abc123", "--deny"]) == 0
    assert "denied" in capsys.readouterr().out
    body = json.loads(api[-1].content)
    assert body == {"approve": False}


def test_approve_unknown_id(
    api: list[httpx.Request], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["approve", "nope"]) == 1
    assert "Unknown approval" in capsys.readouterr().out
