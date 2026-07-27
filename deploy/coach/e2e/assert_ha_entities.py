#!/usr/bin/env python3
"""Prove RV-C discovery entities materialize *inside* Home Assistant (#88).

The nightly coach-sim e2e already proves the bridge publishes HA discovery
payloads to the broker. This closes the last gap in that chain: that HA
actually *ingests* those payloads into live entities. Doing so needs an
authenticated HA — hence the "pre-baked /config auth fixture" the RV epic
(#75) tracked as the remaining piece.

Rather than commit a hand-authored ``.storage`` fixture (a signed long-lived
JWT plus a config-entries blob, both pinned to one HA build's storage schema
and prone to silent "repair" on version bumps), this drives HA's *runtime*
onboarding + config-flow REST APIs, which are stable across releases:

  1. onboard the owner user            -> POST /api/onboarding/users
  2. exchange the auth code for a token -> POST /auth/token
  3. finish the remaining onboarding steps (leave onboarding mode)
  4. add the MQTT integration pointed at the sim broker via the config flow
  5. poll /api/states until an RV-C discovery entity appears (or fail loud)

Stdlib only (urllib + json) so it runs on a bare runner with no pip install.
Talks to the host-networked HA at $HA_URL (default http://127.0.0.1:8123).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")
# HA requires client_id/redirect_uri to be an http(s) URL on the same host.
CLIENT_ID = f"{HA_URL}/"
MQTT_BROKER = os.environ.get("E2E_MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.environ.get("E2E_MQTT_PORT", "1883"))
# The tank device the broker-topic assertions already key on
# (homeassistant/device/rvc_refcoach_tank_status_0/config); its HA entity ids
# slugify to sensor.rv_c_tank_status_0_*.
ENTITY_MATCH = os.environ.get("E2E_ENTITY_MATCH", "tank_status")

_OWNER = {"name": "E2E Owner", "username": "e2e", "password": "e2e-only-password"}


def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: object | None = None,
    form_body: dict[str, str] | None = None,
) -> tuple[int, object]:
    """One HTTP call. Returns (status, parsed-json-or-raw-text)."""
    url = f"{HA_URL}{path}"
    headers = {"Accept": "application/json"}
    data: bytes | None = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        data = urllib.parse.urlencode(form_body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as exc:  # non-2xx still carries a useful body
        body = exc.read().decode()
        status = exc.code
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


def _die(msg: str, detail: object = "") -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    if detail != "":
        print(
            json.dumps(detail, indent=2) if not isinstance(detail, str) else detail,
            file=sys.stderr,
        )
    sys.exit(1)


def wait_for_ha() -> None:
    """Block until HA answers, up to ~2 min (image is already pulled by now)."""
    for _ in range(60):
        try:
            status, _ = _request("GET", "/api/onboarding")
            if status == 200:
                return
        except urllib.error.URLError:
            pass
        time.sleep(2)
    _die("Home Assistant never came up")


def onboard() -> str:
    """Create the owner, finish onboarding, return an access token."""
    status, body = _request(
        "POST",
        "/api/onboarding/users",
        json_body={"client_id": CLIENT_ID, "language": "en", **_OWNER},
    )
    if status != 200 or not isinstance(body, dict) or "auth_code" not in body:
        _die("onboarding/users did not return an auth_code", body)
    auth_code = body["auth_code"]

    status, body = _request(
        "POST",
        "/auth/token",
        form_body={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
        },
    )
    if status != 200 or not isinstance(body, dict) or "access_token" not in body:
        _die("auth/token did not return an access_token", body)
    token = body["access_token"]

    # Leave onboarding mode. Each step is best-effort: a fresh install may have
    # nothing to configure, and a step already done returns non-200 harmlessly.
    for step, payload in (
        ("core_config", {}),
        ("analytics", {}),
        ("integration", {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID}),
    ):
        st, _ = _request(
            "POST", f"/api/onboarding/{step}", token=token, json_body=payload
        )
        print(f"onboarding/{step}: {st}")
    return token


def configure_mqtt(token: str) -> None:
    """Add the MQTT integration via the config flow, pointed at the sim broker."""
    status, flow = _request(
        "POST",
        "/api/config/config_entries/flow",
        token=token,
        json_body={"handler": "mqtt", "show_advanced_options": False},
    )
    if status not in (200, 201) or not isinstance(flow, dict) or "flow_id" not in flow:
        _die("could not start the MQTT config flow", flow)
    flow_id = flow["flow_id"]

    # First step is the broker form; some HA builds add follow-up option steps.
    # Submit broker/port, then accept defaults on any further form until the
    # flow creates the entry (or aborts because one already exists).
    step_body: dict[str, object] = {"broker": MQTT_BROKER, "port": MQTT_PORT}
    for _ in range(5):
        status, result = _request(
            "POST",
            f"/api/config/config_entries/flow/{flow_id}",
            token=token,
            json_body=step_body,
        )
        if not isinstance(result, dict):
            _die("unexpected MQTT flow response", result)
        kind = result.get("type")
        if kind == "create_entry":
            print(f"MQTT entry created: {result.get('title')}")
            return
        if kind == "abort":
            # single_config_entry already present == success for our purposes
            print(f"MQTT flow aborted (reason={result.get('reason')}) — configured")
            return
        if kind == "form":
            step_body = {}  # accept defaults for any extra option step
            continue
        _die("MQTT flow ended in an unexpected state", result)
    _die("MQTT config flow did not converge")


def assert_entity(token: str) -> None:
    """Poll /api/states until an RV-C discovery entity shows up."""
    deadline = 60  # HA processes retained discovery within a few seconds
    for _ in range(deadline // 3):
        status, states = _request("GET", "/api/states", token=token)
        if status != 200 or not isinstance(states, list):
            _die("could not read /api/states", states)
        matches = [
            s["entity_id"]
            for s in states
            if isinstance(s, dict) and ENTITY_MATCH in s.get("entity_id", "")
        ]
        if matches:
            print(f"PASS: RV-C entities materialized in HA: {matches}")
            return
        time.sleep(3)
    _die(
        f"no entity matching {ENTITY_MATCH!r} appeared in HA — "
        "MQTT discovery was not ingested"
    )


def main() -> None:
    wait_for_ha()
    token = onboard()
    configure_mqtt(token)
    assert_entity(token)


if __name__ == "__main__":
    main()
