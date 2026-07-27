# ADR-011: Home Assistant as the Hardware Abstraction Layer

## Status

Accepted

## Context

The RV reference deployment (ADR-010) requires Astrocyte to see and control
physical devices: RV-C multiplex devices (lights, HVAC, tanks) behind the
Firefly system, the Victron Cerbo GX energy system, and whatever sensors get
added later. Astrocyte's own value is the layer above devices — agents, unified
search, and policy-gated automation (ADR-007, ADR-014) — not re-implementing
device drivers.

Home Assistant (HA) is the de-facto open-source home-automation platform
(Apache-2.0): a mature entity/device model, thousands of integrations
(including a native `victron_gx` integration as of HA 2026.5), MQTT device
discovery, a recorder with long-term statistics, dashboards, mobile companion
apps with push notifications, and an automation engine.

The question is where the boundary sits between HA and Astrocyte.

## Decision

**Home Assistant is the hardware abstraction layer; Astrocyte is the brain.**

- HA owns *all* device/protocol integrations. Devices reach HA either through
  its native integrations (Victron Cerbo GX via `victron_gx` over MQTT) or
  through Astrocyte-provided protocol bridges that speak MQTT with HA device
  discovery (the RV-C bridge, ADR-012).
- Astrocyte never speaks a device protocol directly. It consumes HA's entity
  model through a first-party **HA MCP server** (`astrocyte.ha.mcp`, per
  ADR-007) exposing entity state, history, long-term statistics, and a single
  policy-gated `call_service` actuation tool (ADR-014), plus a
  `HomeAssistantConnector` (DataConnector) that feeds entity snapshots into the
  future RAG ingestion pipeline.
- HA runs as a **container** (`home-assistant` image) in the coach compose
  stack — not Home Assistant OS — because the coach node also runs the
  Astrocyte stack, and Astrocyte manages the adjacent services (Mosquitto,
  PostgreSQL) itself. Losing HA OS add-ons is acceptable for the same reason.
- HA is deployed via a compose profile now and becomes a curated app when the
  app registry lands (ADR-010).

## Consequences

### Positive Consequences

- **Leverage**: thousands of battle-tested integrations, dashboards, mobile
  push, and an automation engine for free; Astrocyte code stays focused on
  agents and policy.
- **Clean seam**: the HA entity model is a stable, documented API; device
  churn (new sensors, replaced hardware) never touches Astrocyte core.
- **Degraded-mode UX**: even with every Astrocyte service down, HA still gives
  the owner dashboards and manual control.
- **License-compatible**: HA is Apache-2.0; orchestrating it from an AGPL-3.0
  project is clean.

### Negative Consequences

- **Two systems**: HA configuration (YAML, integrations) becomes part of the
  deployment surface Astrocyte must manage and back up (`/config` volume).
- **Indirection**: agent reads/writes traverse Astrocyte → HA → MQTT → device;
  debugging spans more layers.
- **No HA supervisor backups** (container mode): Astrocyte's backup pillar
  must cover HA's `/config` volume and the recorder database (phase-3).

### Risks and Mitigations

- **Risk**: HA API changes break the MCP server.
- **Mitigation**: pin the HA image tag in compose; the HA client targets the
  stable REST/WebSocket APIs; e2e tests run against the pinned image.

- **Risk**: HA becomes a single point of failure for telemetry.
- **Mitigation**: the MQTT spine (ADR-012) retains state independently of HA;
  HA restarts re-hydrate from retained topics and discovery re-publish.

## Alternatives Considered

### Astrocyte-native sensor subsystem (no HA)

**Description**: Astrocyte speaks RV-C/CAN and Victron protocols directly,
with its own entity model, storage, dashboards, and automations.

**Pros**: single system; purest MCP-first story; no HA dependency.
**Cons**: re-implements years of HA work (device model, recorder, dashboards,
mobile apps, Victron integration); every new device becomes Astrocyte code.
**Why Not Chosen**: enormous scope for negative differentiation — Astrocyte's
value is above the device layer.

### HA's built-in MCP server integration

**Description**: HA ships an `mcp_server` integration; Astrocyte could consume
it instead of building its own.

**Pros**: zero code.
**Cons**: it exposes only the Assist API (conversational intents) — no entity
history, no long-term statistics, no tool granularity, and no place to enforce
Astrocyte's actuation policy (ADR-014). Policy enforcement must live in a
server Astrocyte controls.
**Why Not Chosen**: functionally insufficient and un-gateable.

### MQTT-only integration (Astrocyte reads the bus, HA is optional UI)

**Description**: both HA and Astrocyte consume the MQTT spine as peers;
Astrocyte builds its own entity model from raw topics.

**Pros**: fully decoupled from HA.
**Cons**: Astrocyte re-derives entity semantics HA already computes (device
classes, units, availability, statistics); Victron would need a custom bridge
since its native path is an HA integration.
**Why Not Chosen**: duplicates HA's entity model without removing the HA
dependency in practice.

## Related Decisions

- ADR-007: MCP-First Architecture (the HA MCP server is its first shipped
  server)
- ADR-010: RV Reference Deployment
- ADR-012: RV-C Telemetry Architecture (the bridge that feeds HA)
- ADR-014: Agent Actuation Safety Policy (gates the `call_service` tool)

## Notes

Authentication uses an HA long-lived access token supplied via environment
(`HA_TOKEN`); transport is HTTP/WebSocket over the coach's internal Docker
network or the tailnet (ADR-013). The HA MCP server is mounted into the
existing FastAPI app (`/mcp/ha`) via FastMCP's `http_app()` so it rides the
existing container, healthcheck, and (interim) bearer-token auth (ADR-014).
