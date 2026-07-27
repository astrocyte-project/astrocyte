#!/usr/bin/env python3
"""Move RV-C entity_ids onto the names the coach instance map now gives them.

Clearing retained discovery (`astro-rvc-bridge --reset-discovery`) is **not**
enough on a Home Assistant that has already registered these entities. HA keeps
a `deleted_entities` record keyed by `unique_id` and restores the old entity_id
whenever that unique_id reappears — so a fixture renamed in the map comes back
under its old id, however many times discovery is republished. The id has to be
moved through the entity registry, which is what this does.

    docker compose exec -T api python - < rename_entities.py           # dry run
    docker compose exec -T api python - < rename_entities.py --apply
    docker compose exec -T api python - < rename_entities.py --show    # audit

Targets are computed from HA's *own* registries rather than from a copy of the
instance map, so this cannot drift out of sync with the map: HA builds an
entity_id from the device's area, the device name, and the entity name, and
that is exactly what is reconstructed here. Only entities whose unique_id
carries the bridge's prefix are touched; every other integration is left alone.
Renaming drops the recorder history attached to the old id.

Device areas are repaired first, from the retained discovery payloads on the
broker. HA applies `suggested_area` only when it *first* creates a device, so a
device restored from `deleted_devices` after a discovery reset comes back with
whatever area it had at deletion — area-less, for any zone named after its first
registration. Since the area is part of the generated entity_id, renaming without
repairing it would produce `sensor.mid_ac_*` where the map means
`sensor.galley_mid_ac_*`.

Idempotent: entities already on their target id are skipped, so a re-run after
more devices re-register only moves the new arrivals.
"""

import asyncio
import contextlib
import json
import os
import re
import sys
from urllib.parse import urlparse

import websockets

URL = "ws://127.0.0.1:8123/api/websocket"
TOKEN = os.environ["ASTROCYTE_HA_TOKEN"]
PREFIX = os.environ.get("ASTROCYTE_RVC_UNIQUE_ID_PREFIX", "rvc_")
MQTT_URL = os.environ.get("ASTROCYTE_RVC_MQTT_URL", "mqtt://127.0.0.1:1883")
#: How long to let the broker replay retained discovery configs.
COLLECT_SECONDS = 3.0
APPLY = "--apply" in sys.argv
SHOW = "--show" in sys.argv


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class Client:
    """Minimal request/response wrapper over HA's WebSocket API."""

    def __init__(self, ws: object) -> None:
        self._ws = ws
        self._id = 0

    async def call(self, **payload: object) -> object:
        self._id += 1
        payload["id"] = self._id
        await self._ws.send(json.dumps(payload))
        while True:
            message = json.loads(await self._ws.recv())
            if message.get("id") == self._id and message.get("type") == "result":
                if not message.get("success"):
                    raise RuntimeError(message.get("error"))
                return message["result"]


def expected_entity_id(
    entry: dict, device: dict | None, area_name: str | None
) -> str | None:
    """The entity_id HA would generate for this entry today, or None.

    Mirrors HA's `has_entity_name` composition: the area is prefixed, then the
    device name, then the entity's own name — which is absent for the single
    entity that *is* its device (a light), and present for each field of a
    multi-entity device (a sensor).
    """
    domain = entry["entity_id"].split(".", 1)[0]
    device_name = None
    if device is not None:
        device_name = device.get("name_by_user") or device.get("name")
    if not device_name:
        return None
    parts = [area_name, device_name, entry.get("original_name")]
    return f"{domain}." + "_".join(slug(p) for p in parts if p)


async def retained_areas() -> dict[str, str]:
    """`identifier -> suggested_area`, read from the broker's retained configs.

    HA honours `suggested_area` only when it *first* creates a device. A device
    restored from `deleted_devices` — which is what happens after a discovery
    reset — comes back with whatever area it had when it was deleted, so zones
    named after their first registration stay area-less no matter how often the
    payload is republished. The retained discovery config carries the intended
    area, so it is the source of truth for repairing them.
    """
    import aiomqtt

    url = urlparse(MQTT_URL)
    kwargs: dict[str, object] = {
        "hostname": url.hostname or "127.0.0.1",
        "port": url.port or 1883,
    }
    if os.environ.get("MQTT_USERNAME"):
        kwargs["username"] = os.environ["MQTT_USERNAME"]
        kwargs["password"] = os.environ.get("MQTT_PASSWORD", "")

    found: dict[str, str] = {}
    async with aiomqtt.Client(**kwargs) as mqtt:
        await mqtt.subscribe("homeassistant/device/+/config")
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(COLLECT_SECONDS):
                async for message in mqtt.messages:
                    if not message.payload:
                        continue
                    try:
                        payload = json.loads(message.payload)
                    except ValueError:
                        continue
                    device = payload.get("device") or {}
                    area = device.get("suggested_area")
                    for ident in device.get("identifiers") or []:
                        if area and str(ident).startswith(PREFIX):
                            found[str(ident)] = area
    return found


async def restore_areas(client: "Client", devices: list, areas: list) -> dict[str, str]:
    """Put devices back in the area their discovery payload asks for.

    Returns `device_id -> area name` for every device repaired, so a dry run can
    compute ids against the state `--apply` *would* produce rather than the
    unrepaired one — otherwise the preview would show area-less targets and
    disagree with what actually happens.
    """
    wanted = await retained_areas()
    if not wanted:
        print("no retained discovery found — skipping area repair\n")
        return {}

    area_id_by_name = {a["name"].casefold(): a["area_id"] for a in areas}
    area_name_by_id = {a["area_id"]: a["name"] for a in areas}
    repairs = []
    for device in devices:
        idents = {str(i[1]) for i in device.get("identifiers") or [] if len(i) > 1}
        area = next((wanted[i] for i in idents if i in wanted), None)
        if not area:
            continue
        current = area_name_by_id.get(device.get("area_id"))
        # Repair a *wrong* area as well as a missing one. Correcting a map moves
        # devices between rooms, and HA applies `suggested_area` only at first
        # creation — so a re-mapped fixture keeps the room it was first filed
        # under, which then feeds a wrong entity_id.
        if current is None or current.casefold() != area.casefold():
            repairs.append((device, area))

    if not repairs:
        return {}

    for device, area in repairs:
        name = device.get("name_by_user") or device.get("name")
        was = area_name_by_id.get(device.get("area_id")) or "none"
        print(f"{'area  ' if APPLY else '  would set area'}  {name}: {was} -> {area}")
        if not APPLY:
            continue
        area_id = area_id_by_name.get(area.casefold())
        if area_id is None:
            created = await client.call(type="config/area_registry/create", name=area)
            area_id = created["area_id"]
            area_id_by_name[area.casefold()] = area_id
        await client.call(
            type="config/device_registry/update",
            device_id=device["id"],
            area_id=area_id,
        )
    print(f"{'repaired' if APPLY else 'would repair'} {len(repairs)} device areas\n")
    return {device["id"]: area for device, area in repairs}


async def main() -> int:
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            print("auth failed — check ASTROCYTE_HA_TOKEN")
            return 1

        client = Client(ws)
        entities = await client.call(type="config/entity_registry/list")
        devices = await client.call(type="config/device_registry/list")
        areas = await client.call(type="config/area_registry/list")

        repaired = await restore_areas(client, devices, areas)

        # Re-read: repairing areas changes what the ids should be.
        devices = await client.call(type="config/device_registry/list")
        areas = await client.call(type="config/area_registry/list")

        area_by_id = {a["area_id"]: a["name"] for a in areas}
        device_by_id = {d["id"]: d for d in devices}

        planned, resolved = [], []
        for entry in entities:
            if not str(entry.get("unique_id") or "").startswith(PREFIX):
                continue
            device = device_by_id.get(entry.get("device_id"))
            area_id = entry.get("area_id") or (device or {}).get("area_id")
            # `repaired` covers the dry-run case, where the area assignment has
            # not been written yet but would be before any rename happens.
            area_name = repaired.get((device or {}).get("id")) or area_by_id.get(
                area_id
            )
            want = expected_entity_id(entry, device, area_name)
            if want:
                resolved.append((entry["entity_id"], want))
            if want and want != entry["entity_id"]:
                planned.append((entry["entity_id"], want))

        if SHOW:
            # Audit mode: every RV-C entity and the id its map name implies,
            # so a "nothing to rename" result can be told apart from a lookup
            # that silently resolved nothing.
            for current, want in sorted(resolved):
                mark = "ok " if current == want else "MOVE"
                print(f"{mark} {current}\n     -> {want}")
            print(
                f"\n{len(resolved)} RV-C entities resolved, "
                f"{len(planned)} need renaming"
            )
            return 0

        if not planned:
            print("nothing to rename — every RV-C entity is already on its map name")
            return 0

        # A collision would make HA silently append _2, so it has to be
        # resolved rather than walked into.
        taken = {e["entity_id"] for e in entities}
        moving = {old for old, _ in planned}
        wanted = [new for _, new in planned]
        duplicated = {n for n in wanted if wanted.count(n) > 1}
        # A target held by an entity that is *itself* moving is a rotation and
        # resolves on its own; one held by anything else is a real conflict.
        external = {n for n in wanted if n in taken and n not in moving}
        if external or duplicated:
            print("REFUSING — these target ids are taken or requested twice:")
            for name in sorted(external | duplicated):
                print(f"  {name}")
            return 1

        # Correcting a map permutes ids (A wants B's id while B wants C's).
        # Renaming in place collides part-way through whatever the order, so
        # anything caught in a rotation goes via a temporary id first.
        rotating = [(old, new) for old, new in planned if new in moving]
        direct = [(old, new) for old, new in planned if new not in moving]

        for old, new in sorted(direct):
            print(
                f"{'rename' if APPLY else '  would rename'}  {old}\n"
                f"            -> {new}"
            )
            if APPLY:
                await client.call(
                    type="config/entity_registry/update",
                    entity_id=old,
                    new_entity_id=new,
                )

        if rotating:
            print(
                f"\n{'resolving' if APPLY else '  would resolve'} "
                f"{len(rotating)} id(s) caught in a rotation, via temporaries:"
            )
            # Two passes, not one round trip each: park every rotating entity
            # before releasing any of them, or the first unpark lands on an id
            # its own cycle has not vacated yet.
            parked_for = []
            for index, (old, new) in enumerate(sorted(rotating)):
                parked = f"{old.split('.', 1)[0]}.astro_rename_tmp_{index}"
                parked_for.append((parked, new))
                print(f"  {old}\n    -> {parked} -> {new}")
                if APPLY:
                    await client.call(
                        type="config/entity_registry/update",
                        entity_id=old,
                        new_entity_id=parked,
                    )
            for parked, new in parked_for:
                if APPLY:
                    await client.call(
                        type="config/entity_registry/update",
                        entity_id=parked,
                        new_entity_id=new,
                    )

        verb = "renamed" if APPLY else "would rename"
        tail = "" if APPLY else "  (re-run with --apply)"
        print(f"\n{verb} {len(planned)} entities{tail}")
        return 0


raise SystemExit(asyncio.run(main()))
