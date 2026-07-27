#!/usr/bin/env python3
"""Configure Home Assistant's native Energy dashboard from the Victron meters.

Energy prefs are WebSocket-only (no REST), so this runs inside the api container
(which ships `websockets` and has ASTROCYTE_HA_TOKEN in its env), talking to HA
over host-network loopback:

    docker compose exec -T api python - < energy_prefs.py

Idempotent — re-running just overwrites the prefs. Sources:
  solar   = MPPT lifetime yield (kWh)
  grid    = shore import (sensor.shore_energy_import template, AC-in 1 total)
  battery = SmartShunt charged / discharged energy (kWh)
"""

import asyncio
import json
import os
import pathlib

import websockets

URL = "ws://127.0.0.1:8123/api/websocket"
TOKEN = os.environ["ASTROCYTE_HA_TOKEN"]

# HA 2026.6 uses a flat grid source (stat_energy_from directly, not flow_from
# lists). cost_adjustment_day is required on the grid source.
# Entity ids differ per installation (they come from the victron_gx config
# flow), so they are configuration rather than code: point ASTROCYTE_ENERGY_PREFS
# at a JSON file holding this same structure. The fallback below is the shipped
# example — it will not match a real coach.
PREFS_PATH = os.environ.get(
    "ASTROCYTE_ENERGY_PREFS",
    str(pathlib.Path(__file__).with_name("energy_prefs.example.json")),
)
with open(PREFS_PATH, encoding="utf-8") as fh:
    PREFS = json.load(fh)


async def main() -> None:
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.recv()  # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        auth = json.loads(await ws.recv())
        if auth.get("type") != "auth_ok":
            raise SystemExit(f"auth failed: {auth}")
        await ws.send(json.dumps({"id": 1, "type": "energy/save_prefs", **PREFS}))
        while True:
            resp = json.loads(await ws.recv())
            if resp.get("id") == 1:
                if resp.get("success"):
                    print("energy prefs saved OK")
                else:
                    raise SystemExit(f"save_prefs failed: {resp.get('error')}")
                break


asyncio.run(main())
