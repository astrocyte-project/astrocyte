#!/usr/bin/env python3
"""Poll the coach router's gateway status and push it to VictoriaMetrics as metrics.

Runs on the coach node. Reads OPNsense's dpinger results over the API and writes
Prometheus-format samples to VictoriaMetrics, so WAN latency, jitter, packet loss
and up/down are graphable in Grafana alongside the node_exporter interface counters.

Why here and not on the router: it avoids running a second agent on the
router's modest CPU. The coach node already has a permitted path to the
router's mgmt IP, so no new firewall rule is needed.

Usage (every 30s via the systemd user timer in deploy/coach/systemd/):
    COACH_ROUTER_URL=https://<addr> \\
      coach-gw-metrics.py --api-key-file ~/.config/opnsense-metrics-apikey.txt

Flags:
    --router      router mgmt URL, or COACH_ROUTER_URL (no default: a
                  deployment's address is an input, never baked in here)
    --vm          VictoriaMetrics import URL (default http://127.0.0.1:8428)
    --dry-run     print the metrics instead of pushing

Install steps and the whole design: docs/runbooks/coach-node-provisioning.md §7.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

# dpinger reports these as strings with units, e.g. "12.3 ms" / "0.0 %".
NUMERIC_SUFFIXES = (" ms", " %", "ms", "%")


def parse_number(raw: str) -> float | None:
    """'12.3 ms' -> 12.3 ; '~' or '' -> None (gateway not reporting)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == "~":
        return None
    for suf in NUMERIC_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
            break
    try:
        return float(s)
    except ValueError:
        return None


def sanitise_label(name: str) -> str:
    """OPNsense derives gateway names from interface DESCRIPTIONS, so they can
    contain spaces (e.g. 'WIFIRANGER WAN2_DHCP'). Make them label-safe."""
    out = []
    for ch in name.strip():
        out.append(ch if (ch.isalnum() or ch in "_-") else "_")
    return "".join(out) or "unknown"


def fetch_gateways(base: str, key: str, secret: str, insecure: bool) -> list[dict]:
    url = f"{base.rstrip('/')}/api/routes/gateway/status"
    req = urllib.request.Request(url)
    import base64

    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    ctx = None
    if insecure:
        # OPNsense ships a self-signed cert on its mgmt interface.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read().decode()).get("items", [])


def build_metrics(items: list[dict]) -> str:
    lines = [
        "# HELP coach_gateway_delay_ms WAN gateway RTT as measured by dpinger",
        "# TYPE coach_gateway_delay_ms gauge",
        "# HELP coach_gateway_stddev_ms WAN gateway jitter",
        "# TYPE coach_gateway_stddev_ms gauge",
        "# HELP coach_gateway_loss_ratio WAN gateway packet loss (0-1)",
        "# TYPE coach_gateway_loss_ratio gauge",
        "# HELP coach_gateway_up 1 if the gateway status is online",
        "# TYPE coach_gateway_up gauge",
    ]
    for it in items:
        name = it.get("name") or ""
        if not name:
            continue
        gw = sanitise_label(name)
        labels = f'gateway="{gw}",address="{it.get("address", "")}"'

        delay = parse_number(it.get("delay"))
        stddev = parse_number(it.get("stddev"))
        loss = parse_number(it.get("loss"))
        status = (it.get("status") or "").lower()
        # dpinger uses "none" for a healthy gateway with no alarm.
        up = 1 if status in ("none", "online", "") else 0

        if delay is not None:
            lines.append(f"coach_gateway_delay_ms{{{labels}}} {delay}")
        if stddev is not None:
            lines.append(f"coach_gateway_stddev_ms{{{labels}}} {stddev}")
        if loss is not None:
            lines.append(f"coach_gateway_loss_ratio{{{labels}}} {loss / 100.0}")
        lines.append(f"coach_gateway_up{{{labels}}} {up}")
    return "\n".join(lines) + "\n"


def push(vm_base: str, payload: str) -> None:
    url = f"{vm_base.rstrip('/')}/api/v1/import/prometheus"
    req = urllib.request.Request(url, data=payload.encode(), method="POST")
    req.add_header("Content-Type", "text/plain")
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status not in (200, 204):
            raise SystemExit(f"VictoriaMetrics returned {resp.status}")


def main() -> int:
    ap = argparse.ArgumentParser()
    # No default: the router's address identifies a deployment, so it is an
    # input rather than something this file carries. A placeholder default
    # would only be edited on the node, which is how this script and its unit
    # drifted apart in the first place.
    ap.add_argument(
        "--router",
        default=os.environ.get("COACH_ROUTER_URL", ""),
        help="router mgmt URL, e.g. https://<addr> (or set COACH_ROUTER_URL)",
    )
    ap.add_argument("--vm", default="http://127.0.0.1:8428")
    ap.add_argument(
        "--api-key-file", required=True, help="two lines: API key, then API secret"
    )
    ap.add_argument(
        "--insecure",
        action="store_true",
        default=True,
        help="accept the router's self-signed cert (default on)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.router:
        ap.error("pass --router or set COACH_ROUTER_URL")

    with open(args.api_key_file) as fh:
        parts = [ln.strip() for ln in fh if ln.strip()]
    if len(parts) < 2:
        print(
            "api key file must hold key on line 1 and secret on line 2", file=sys.stderr
        )
        return 2
    key, secret = parts[0], parts[1]
    key = key.removeprefix("key=")
    secret = secret.removeprefix("secret=")

    try:
        items = fetch_gateways(args.router, key, secret, args.insecure)
    except urllib.error.URLError as exc:
        # Do not emit partial data: a failed poll should leave a gap, not a zero.
        print(f"gateway poll failed: {exc}", file=sys.stderr)
        return 1

    payload = build_metrics(items)
    if args.dry_run:
        print(payload, end="")
        return 0
    push(args.vm, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
