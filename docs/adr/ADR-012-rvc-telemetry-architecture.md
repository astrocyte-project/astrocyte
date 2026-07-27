# ADR-012: RV-C Telemetry — SocketCAN→MQTT Bridge, MQTT Spine, and Time-Series Storage

## Status

Accepted (amended 2026-07-21, 2026-07-23, 2026-07-24, 2026-07-27 ×2 — see [Amendments](#amendments))

## Context

The coach's Firefly multiplex system exposes an **RV-C** network (the RVIA
standard built on CAN 2.0B at 250 kbit/s) carrying device state and commands:
DC dimmers (lights), thermostats, tank levels, energy management, and more.
Home Assistant has no native RV-C integration, so a bridge is required
(ADR-011). Physical access is a Molex Micro-Fit 3.0 connector on the Firefly
G12/Eclipse module, tapped by an isolated USB CAN adapter running candleLight
firmware (`gs_usb` driver → SocketCAN on Linux).

Telemetry also needs storage for history and trend queries ("is the battery
draining faster than last week?"), and the coach node is a Raspberry Pi 5
writing to an SD card — storage choices have endurance consequences.

Existing open-source RV-C work: `linuxkidd/rvc-monitor-py` and
`spbrogan/rvc2mqtt` (both Apache-2.0, low activity). Their durable artifact is
the community-maintained **`rvc-spec.yml`** DGN decode table; the code itself
is untyped, untested script-grade Python that would not pass this repo's
mypy-strict/coverage gates.

## Decision

Three parts:

### 1. Bridge: `astrocyte.rvc` — typed decoder over a vendored spec table

- **Vendor** the Apache-2.0 `rvc-spec.yml` decode table into
  `src/astrocyte/rvc/spec/` with attribution in `NOTICE` and the file header
  (Apache-2.0 → AGPL-3.0 is one-way compatible).
- **Write our own** typed decoder/encoder engine (`spec.py`, `decoder.py`,
  `encoder.py`) meeting the repo's strict typing and coverage gates.
  `spbrogan/rvc2mqtt` remains a design reference for entity mapping only.
- A standalone asyncio daemon (`astrocyte.rvc.bridge`, console script
  `astro-rvc-bridge`) connects python-can (SocketCAN) to MQTT (aiomqtt).
- **Listen-only by default**: the CAN interface is opened in listen-only mode
  and the command path is disabled until `listen_only: false` is explicitly
  configured — flipped only after on-vehicle validation (see ADR-014 and the
  install runbook). This bounds the blast radius of a live coach bus shared
  with the EMS.

### 2. MQTT spine: Mosquitto + HA device discovery

Mosquitto is the coach node's message bus. The bridge owns the `rvc/`
namespace:

| Topic | Content |
|-------|---------|
| `rvc/state/<dgn_name>/<instance>` | decoded JSON, retained for stateful DGNs |
| `rvc/cmd/<dgn_name>/<instance>` | commands the bridge encodes to CAN (ignored while listen-only) |
| `rvc/cmd/light/<instance>/{switch,brightness}` | HA-facing light command topics (MQTT light entities can't emit the generic JSON form) |
| `rvc/raw/<pgn_hex>` | raw frames (debug/capture flag, off by default) |
| `rvc/bridge/status` | `online`/`offline` availability via MQTT LWT |
| `homeassistant/device/rvc_<coach_id>_<device>/config` | retained HA device-based discovery payloads, re-published on HA birth message |

Discovery uses HA's current **device-based** discovery format with a required
`origin` block and stable `unique_id`s (instability would duplicate entities
in HA on every deploy).

### 3. Time-series: PostgreSQL recorder + HA statistics — no InfluxDB

The HA recorder writes to the coach's shared **PostgreSQL** instance (already
on Astrocyte's roadmap as the application database). HA's **long-term
statistics** (hourly aggregates, kept indefinitely) serve trend queries via
the HA MCP server. No InfluxDB is deployed. Recorder is tuned for SD endurance
(`commit_interval`, `purge_keep_days`, excluded chatty entities). This
supersedes the earlier owner plan of running InfluxDB on the Pi.

## Consequences

### Positive Consequences

- **One data store** on the coach node (Postgres) — one backup target, less
  RAM/IO on the Pi.
- **Typed, tested decode path** that CI can validate against golden fixtures;
  the vendored spec is re-vendorable as the community table improves.
- **Decoupling**: retained MQTT state survives HA and bridge restarts; any
  future consumer (including Astrocyte itself) can subscribe without touching
  the CAN layer.
- **Safety by construction**: TX cannot happen until explicitly enabled.

### Negative Consequences

- **SQL, not TSDB**: ad-hoc analytical queries are weaker than InfluxDB/
  VictoriaMetrics; Grafana-grade dashboards would need a future revisit.
- **Spec-table ceiling**: the community table may not decode Firefly's
  proprietary DGNs; expect iteration after the first real capture.
- **Linux-only bridge**: SocketCAN exists only on Linux. Deliberate — the
  bridge deploys to the Pi; unit tests use python-can's `virtual` bus so the
  suite passes on any developer OS.

### Risks and Mitigations

- **Risk**: Firefly uses proprietary DGNs the spec table can't decode.
- **Mitigation**: unknown DGNs pass through to `rvc/raw` for capture; the
  spec loader accepts local extensions; a post-install issue tracks extending
  the table from real captures.

- **Risk**: SD card wear from Postgres + recorder writes.
- **Mitigation**: recorder tuning (above); NVMe HAT tracked as a hardware
  follow-up.

## Alternatives Considered

### Adopt `rvc2mqtt` / `rvc-monitor-py` wholesale

**Pros**: working code today.
**Cons**: untyped, untested, unmaintained; fails repo quality gates; both
are monitor-oriented with weak command paths.
**Why Not Chosen**: the spec table is the valuable artifact; the engine is
cheaper to write than to rehabilitate.

### InfluxDB 2.x (the original owner plan)

**Pros**: purpose-built TSDB, Grafana-native, HA has an export integration.
**Cons**: an extra always-on service on an 8 GB Pi; a second data store to
back up; InfluxDB 2.x OSS is in maintenance mode with an uncertain 3.x OSS
story.
**Why Not Chosen**: HA statistics cover the agent-facing queries; revisit
(likely VictoriaMetrics) only if dashboard needs outgrow HA.

### VictoriaMetrics / TimescaleDB

**Pros**: modern TSDB (VM) or Postgres-native time-series (Timescale + LTSS).
**Cons**: VM adds a query dialect and service; Timescale requires the
unofficial LTSS custom component with its own maintenance risk.
**Why Not Chosen**: not needed for 1.0's query patterns; documented as the
revisit path.

### CAN → HA via a custom HA integration (no MQTT)

**Pros**: one fewer service (no broker).
**Cons**: couples the decoder to HA's release cycle and Python runtime;
loses the retained-state spine and multi-consumer decoupling; harder to test.
**Why Not Chosen**: MQTT is the established HA ingestion path for bridges and
keeps the decoder independently testable.

## Amendments

### 2026-07-27 — colour fixtures, and per-coach data leaves this repo

A full on-bus mapping pass produced three generalizable results.

**Colour fixtures are a switch plus a channel triplet.** A Firefly RGB fixture
occupies four consecutive `DC_DIMMER_COMMAND_2` instances: the instance a wall
switch broadcasts, immediately followed by its red/green/blue channels
(77 → 78/79/80). On/off and brightness address the switch exactly like a plain
fixture; colour addresses the three channels. The bridge therefore publishes
**one** HA entity per fixture using the JSON light schema rather than four
opaque dimmers, assembling state from all four instances and expanding a colour
command back into up to four writes. Levels are decoded percent, where **125%
(raw 250) is full scale** — that is what this coach's switches broadcast for
"on", so it anchors the 0-255 conversion in both directions.

**A field can be inert even when the spec says otherwise.** `WATERHEATER_STATUS`
reports `ac_element_status` as "no data" in every frame, including while the
electric element is demonstrably running; `operating_modes` is the field that
carries the truth (0 off / 1 burner / 2 electric). This is the same shape as the
inert `DC_DIMMER_STATUS_1` finding: **a field that never varies across states
carries no information, whatever the spec calls it.** Verify against captured
frames before surfacing a field, and record the negative result.

**Ordered narration shifts.** The 2026-07-21 map was built by correlating the
first-ON transition per instance against a narrated list. One missed fixture
shifted every subsequent name by one position, and the error survived a
"re-validated 18/20" review because that review re-checked the same ordering
rather than testing fixtures individually. Ten of twenty entries were wrong. The
method now requires a per-fixture press with its own confirmation, and the
runbook says so. A useful cross-check surfaced too: on this coach **interior
fixtures command at level 250 and exterior ones at 200**, which independently
partitions the two groups.

**Per-coach data moves out of this repo.** Which instance drives which fixture
is deployment inventory, not architecture, so `rvc-instances.yml`, the curated
dashboard, automations and the energy-prefs entity ids are supplied by the
operator's own inventory repo and mounted via `RVC_INSTANCE_MAP`,
`HA_DASHBOARD`, `HA_AUTOMATIONS`, `HA_PACKAGES` and `ASTROCYTE_ENERGY_PREFS`.
This repo ships `*.example.*` counterparts, which are also the defaults the
stack falls back to, so a fresh checkout still starts. HA's timezone moves to
`!env_var TZ` for the same reason — it had drifted to a value that existed only
on the deployed node.

### 2026-07-27 — entity naming is area-relative; discovery is resettable

Home Assistant's `has_entity_name` rules turn a device/entity name pair into the
displayed name **and** the generated entity_id, and the device's area is prefixed
into that id. Publishing the fixture name in both places — which the light path
did — produced `light.living_room_living_room_ceiling_living_room_ceiling`,
"Living Room Ceiling Living Room Ceiling". Verified against a live HA 2026.6 with
throwaway probe devices (issue #151):

| light component `name` | entity_id | friendly name |
|---|---|---|
| the device name | `light.bedroom_probe_bravo_probe_bravo` | Probe Bravo Probe Bravo |
| key omitted | `light.bedroom_probe_alpha_mqtt_lightentity` | Probe Alpha MQTT LightEntity |
| `null` | `light.bedroom_probe_charlie` | Probe Charlie |

So a single-entity device publishes `"name": null` — the entity *is* the device —
and coach-map names are **area-relative** (`Ceiling` in area `Bedroom`), because
HA supplies the area: `light.bedroom_ceiling`. `object_id` is not an escape
hatch; device-based discovery ignores it.

This makes the coach map the single source of naming truth, so
`THERMOSTAT_AMBIENT_STATUS` now draws on the same zone names as
`THERMOSTAT_STATUS_1` — it is the same zone reporting its temperature.

**Consequence: renames need a discovery reset *and* a registry rename.** HA
assigns an entity_id once, at first registration, and keeps it even when the
discovery name changes. `astro-rvc-bridge --reset-discovery` clears this coach's
retained configs (map-derived lights, plus any
`homeassistant/device/rvc_<coach>_*/config` found on the broker) and exits,
superseding the manual `mosquitto_pub -r -n` cleanup the v0.3.3 deploy needed.

That alone does **not** move the ids, which the v0.3.4 deploy established on the
coach: HA keeps a **`deleted_entities` record keyed by `unique_id`** (696 of them
for `rvc_refcoach_*`) and *restores the old entity_id* when that unique_id
reappears. Entities came back as
`light.living_room_living_room_ceiling_living_room_ceiling` after a clean reset,
with `original_name: None` proving the new payload had been applied. Since
`unique_id` stability is load-bearing here — churning it would duplicate every
entity in HA on each deploy — the id has to be moved explicitly through the
entity registry:
`config/homeassistant/rename_entities.py` (`--show` to audit, `--apply` to move).
It derives each target from HA's own area/device/entity registries rather than
from a second copy of the map, so it cannot drift out of sync with it.

A **fresh** deployment needs none of this — it registers on the current names
directly. The cost of the rename is recorder history under the old ids —
acceptable for RV-C telemetry, and it does not touch the Victron entities the
Energy dashboard's long-term statistics use.

**Second consequence: a reset only rebuilds what the bus re-announces.** Sensor
devices are discovered from observed frames, so on a sleeping coach bus they stay
missing until it next wakes — the v0.3.4 deploy dropped from 690 to 257 entities
for exactly this reason, with the retained `rvc/state/#` topics preserved so
values return with the entities. Reset while the bus is live, or accept the gap.

### 2026-07-24 — remaining proprietary DGNs recognized (decode gaps closed)

The 2026-07-23 amendment below classified the two easy buckets (J1939 protocol,
Firefly node-sync). This closes the rest of issue #123: the 14 DGN kinds still
logged as `UNKNOWN` across the 2026-07-21 captures (~49k frames, the final ~10%).
Investigation confirmed **none are standard RV-C DGNs missing from the vendored
table** — every one is vendor-proprietary (J1939 Proprietary-B PGNs `0xFFxx` or
manufacturer DGNs from specific nodes). They are added to `rvc-supplement.yml` as
`internal` (recognized and suppressed), so the decoder now classifies the real
coach bus with **zero `UNKNOWN`** — the clean-decode soak evidence ADR-014 / the
CAN-tap runbook §8 require before TX is enabled is no longer diluted by noise.

Names encode only what the capture evidence supports; unidentified nodes get a
neutral `PROP_*` name keyed on the DGN. One entry has a promotion path:
`DC_DIMMER_CHANNEL_STATUS` (15FCE, source `0x9B` — the lighting controller)
carries genuine per-channel state (a byte-7 on/off bit tracked physical toggles),
but its channel space does not line up with the `DC_DIMMER_COMMAND_2` instance
map that HA lights are built from, so it stays `internal` until the RGB on-bus
reconcile (#122) maps channels → fixtures — at which point it can become `data`.
This does **not** change the light path, the MQTT spine, or the TX safety model.

### 2026-07-23 — lights come from DC_DIMMER_COMMAND_2, not STATUS_1

The 2026-07-23 on-bus session on coach refcoach established that this coach's
**`DC_DIMMER_STATUS_1` is inert**: across 11 broadcast sweeps, with lights
actively toggled and the RGB accent animation running, all 36 instances (32–67)
were byte-for-byte static — `master_brightness` reads `0xFF` (unavailable) and
the R/G/B bytes are a fixed per-instance colour-config ramp. STATUS_1 broadcasts
a configuration pattern every ~133 s, **not live light state.** Building HA
`light.*` from it (the original Decision §2 / ADR-011 path) therefore produces
entities that can neither reflect state nor be reconciled to fixtures.

This amends the light path (it does **not** touch telemetry, the MQTT spine, or
the listen-only/TX safety model):

- **HA lights are built from the coach instance map, keyed on their
  `DC_DIMMER_COMMAND_2` instance.** The wall switches broadcast COMMAND_2 on
  every toggle (with the level), so the bridge tracks each mapped light's state
  from observed command traffic and controls it on the same instance — one
  instance space, no translation. Discovery for all mapped lights is published
  at bridge startup and on HA's birth message (the map is known up front; it no
  longer waits for a frame).
- **`DC_DIMMER_STATUS_1` (1FFBB) is reclassified `internal`** in the local
  supplement so its 36 static-config instances stay out of MQTT/HA.
- The command-instance map was recovered 2026-07-21 and **re-validated live
  2026-07-23** (18/20 fixtures confirmed exactly). Command DGNs are still not
  discovered as devices; only the derived per-light state is published.

Consequence: a mapped light shows state only after the bridge has observed one
command for it (a physical toggle or our own TX), and RGB fixtures + scene
buttons (the animated 78–108 range) remain a follow-up (#122). This is
coach-specific behaviour appropriate to the reference deployment; a future coach
with a functional STATUS_1 would revisit the classification.

### 2026-07-23 — local spec supplement, decode categories, PDU1 addressing

The first real-bus captures on coach refcoach (2026-07-21) surfaced 28 DGN kinds
the vendored table logged as `UNKNOWN` (issue #123). They split cleanly into
standard J1939 protocol plumbing (transport protocol, address claim, request,
ACK) and high-volume Firefly module↔module sync — neither is coach telemetry,
but drowning them in `UNKNOWN` hides real decode gaps. This amendment refines
Decision §1 (the spec-driven decoder) on three points; it **does not reverse**
anything.

1. **Local supplement, vendored file untouched.** The upstream `rvc-spec.yml`
   stays byte-identical to its vendored commit (re-vendorability, *Risks*). Our
   additions live in a sibling `rvc-supplement.yml` (AGPL, ours) that the loader
   merges on top (`RvcSpec.load_vendored`); the supplement wins on a key
   collision, and a test asserts the collision set is intentional.

2. **DGN categories.** Each definition carries a `category` —
   `data` (decoded, published, HA-discovered; the default, so the vendored table
   is unchanged), `protocol` (J1939 plumbing), or `internal` (Firefly node-sync
   chatter). The bridge publishes only `data`; `protocol`/`internal` are counted
   and dropped rather than logged as `UNKNOWN`. Per-category decode counters give
   the "decodes cleanly for days" soak evidence the CAN-tap runbook §8 and
   ADR-014 require before TX is enabled.

3. **PDU1 (addressed) DGNs.** For J1939 PDU1 frames (PDU-Format byte < `0xF0`)
   the low DGN byte is the destination address, not part of the PGN. The decoder
   looks up the destination-cleared PGN (so one `0EC00` entry covers every
   `0ECxx`) and records the real destination on
   `DecodedMessage.destination_address`.

### 2026-07-21 — optional VictoriaMetrics + Grafana observability profile

The "revisit if dashboard needs outgrow HA" trigger named in *Alternatives
Considered* (InfluxDB / VictoriaMetrics) has fired: energy telemetry (Victron
battery/solar/tanks) is more useful graphed over time than HA's built-in
history and long-term-statistics views allow. An **optional** `observability`
compose profile adds **VictoriaMetrics** as the time-series store — the revisit
candidate this ADR anticipated — with Grafana on top (PR #117; issues #33, #94).

This **amends but does not reverse** Decision §3. The default posture is
unchanged: the HA recorder still writes to Postgres, and HA long-term
statistics remain the **primary, agent-facing** trend store queried via the HA
MCP server. VictoriaMetrics is **additive and opt-in** — it does not run unless
`--profile observability` is selected, and it does not replace the recorder or
change the backup story for the default deployment. It scrapes HA's built-in
`prometheus:` exporter (a read path over already-recorded state), the API's
`/metrics`, and container/host exporters; nothing writes to it directly.

The negative consequence *"SQL, not TSDB: Grafana-grade dashboards would need a
future revisit"* is what this resolves. The offsetting cost — a second store's
RAM and SD writes on the 8 GB Pi, the reason §3 avoided a TSDB — is accepted
under these bounds and remains real:

- **Opt-in**, so the minimal coach stays single-store.
- VictoriaMetrics is far lighter than InfluxDB and compresses aggressively; a
  modest 30 s scrape interval limits SD write amplification.
- It reinforces the existing **NVMe HAT** hardware follow-up (see *Risks and
  Mitigations*) — the recommended path once the observability profile is run
  continuously rather than for spot investigations.
- All services bind loopback only (ADR-014 posture); reached via the tailnet /
  SSH tunnel, never the coach LAN.

VictoriaMetrics was chosen over InfluxDB (maintenance-mode 2.x, uncertain 3.x
OSS) and Timescale+LTSS (unofficial custom component) for the reasons already
recorded in *Alternatives Considered*; it speaks the Prometheus query API, so
Grafana treats it as a standard Prometheus datasource with no bespoke dialect
lock-in.

## Related Decisions

- ADR-001: Base Platform (Docker Compose; the bridge is a compose service)
- ADR-011: Home Assistant as the Hardware Abstraction Layer
- ADR-013: Multi-Node Topology (where the broker and consumers live)
- ADR-014: Agent Actuation Safety Policy (the command path's gate)

## Notes

CAN interface setup (`ip link set can0 up type can bitrate 250000
listen-only on`) is host-level, managed by a systemd unit documented in the
coach provisioning runbook. The bridge consumes an already-up interface. The
`rvc/raw` capture flag plus `candump` provide the fixture-recording path used
to replace synthetic test fixtures with real coach data after installation.
