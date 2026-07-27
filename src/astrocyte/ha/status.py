"""The curated coach snapshot behind ``rv_status()`` and ``aios rv status``.

Heuristic grouping over the HA entity population: the coach's HA config names
its entities descriptively (battery/fuel/tank/…), and anything not matched
still shows up in the per-domain counts. Pure function — trivially testable.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

_GROUPS: dict[str, tuple[str, ...]] = {
    "battery": ("battery", "soc", "dc_source"),
    "fuel": ("fuel",),
    "tanks": ("tank",),
    "climate": ("thermostat", "climate", "temperature", "ac_"),
    "power": ("inverter", "generator", "shore", "leg"),
}


def _entity_summary(state: dict[str, Any]) -> dict[str, Any]:
    attributes = state.get("attributes", {})
    summary: dict[str, Any] = {
        "entity_id": state.get("entity_id"),
        "state": state.get("state"),
    }
    if attributes.get("friendly_name"):
        summary["name"] = attributes["friendly_name"]
    if attributes.get("unit_of_measurement"):
        summary["unit"] = attributes["unit_of_measurement"]
    return summary


def collect_rv_status(states: list[dict[str, Any]]) -> dict[str, Any]:
    """One-call coach snapshot for agents and the CLI."""
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in _GROUPS}
    domains: Counter[str] = Counter()
    lights_on = 0

    for state in states:
        entity_id = str(state.get("entity_id", ""))
        if not entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        domains[domain] += 1
        if domain == "light" and state.get("state") == "on":
            lights_on += 1
        haystack = " ".join(
            [entity_id, str(state.get("attributes", {}).get("friendly_name", ""))]
        ).lower()
        for group, needles in _GROUPS.items():
            if any(needle in haystack for needle in needles):
                groups[group].append(_entity_summary(state))
                break

    return {
        **{group: entities for group, entities in groups.items() if entities},
        "lights_on": lights_on,
        "entity_counts": dict(domains),
    }
