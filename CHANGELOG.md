# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Package versions are derived from `v*` git tags (see
[ADR-008](docs/adr/ADR-008-dev-tooling-cicd.md)).

## [Unreleased]

### Security

- **The RV-C bridge's generic command path is now default-deny** (ADR-014
  amended). `handle_command` gated only on `listen_only`: its mapped-light
  branch refuses instances absent from the coach map, but its generic branch,
  `rvc/cmd/<dgn_name>/<instance>`, would encode **any** of the spec's 69 command
  DGNs from raw fields — including `GENERATOR_COMMAND`, `SLIDE_COMMAND`,
  `LEVELING_CONTROL_COMMAND`, `CHASSIS_MOBILITY_COMMAND` and
  `DC_DISCONNECT_COMMAND` — reachable by anything on the node, since the broker
  is anonymous on loopback. Clearing `listen_only` to enable light control would
  therefore have exposed generator start/stop, which ADR-014 places in `deny`.
  The path is now allowlisted by DGN name via `ASTROCYTE_RVC_COMMAND_ALLOWLIST`,
  **empty by default**, with refusals counted and logged. Mapped-light control
  is unaffected.

### Added

- **The System Health dashboard graphs its host metrics over time.** The CPU,
  RAM, root-disk and SoC-temp tiles answered "what is it now" but not "how did
  it get there". A history row under them plots the same four queries — CPU,
  RAM and disk share one percent axis, SoC temp gets its own panel with the
  warn/critical thresholds drawn in.

- **Engine Preheat is decoded.** `1FE99` is promoted from `internal` to `data`
  as `AQUAHOT_HEAT_SOURCE_STATUS`, carrying burner-enabled, electric-enabled and
  engine-preheat-active. It is the only frame on the bus that reports preheat —
  nothing in `WATERHEATER_STATUS` carries it, which is why earlier decode passes
  could not find it. Decoded from a 74,713-frame capture taken while each switch
  was thrown one at a time; the frame's own byte 1 reproduces
  `WATERHEATER_STATUS` `operating modes` at every transition, which is what
  makes the preheat bit a reading rather than a guess.

### Fixed

- **Per-container metrics went missing on Docker 29.x, and the dashboard showed
  it as an empty panel rather than an error.** Docker 29 defaults to the
  containerd image store (`Storage Driver: overlayfs`), which retired the
  `/var/lib/docker/image/<driver>/layerdb` path cAdvisor used to resolve a
  container's read-write layer. cAdvisor v0.49.1 fails that lookup for every
  container and registers none of them, yet the scrape still returns 200 and
  `up` stays 1 — it just emits bare cgroups with no `name=`/`image=` label, so
  the System Health container panels matched nothing and read as "no data".
  cAdvisor moves to `ghcr.io/google/cadvisor:v0.60.5`, which carries the
  upstream fix (google/cadvisor#3643 / #3709, released in v0.56.0). Verified on
  the reference coach: all 11 stack containers now report by name. Deploy note:
  the image is on ghcr.io because gcr.io stopped publishing after v0.49.x.

- **cAdvisor's healthcheck probed another service's port.** The image's built-in
  healthcheck targets `:8080`, which this deployment reassigns to UniFi's inform
  port; UniFi answered 404 and the container reported `unhealthy` indefinitely
  while collecting normally. It now probes `:8081/healthz`, where cAdvisor
  actually listens.

- **cAdvisor no longer scans the eMMC for filesystem metrics.** Per-container
  disk accounting walks every overlayfs layer on a timer — 1.1-4.6 s per pass on
  coach-node's card, which the rest of this stack goes out of its way to spare.
  Disabled via `-disable_metrics=disk`; host filesystems come from node-exporter
  and the cheap blkio counters are unaffected. `-store_container_labels=false`
  drops a further ~660 series of mostly-empty label strings, and
  `-docker_only=true` skips the systemd service cgroups no panel queries.

- **`WATERHEATER_STATUS` `burner status` was mislabelled.** The vendored table
  names its active value "ac element is active", on a field that tracks the
  diesel burner: it went active on the same timestamp as `operating modes` →
  combustion, cleared with it, and stayed off through every electric-only
  period. Read literally the old label invites building an "electric element on"
  indicator out of a burner field — and nothing anywhere reports the electric
  element's run state, since `ac element status` is a *fault* field. Corrected
  via a supplement override, leaving the vendored table byte-identical for
  re-vendoring.

- **A light's level no longer renders as fact before the bridge has seen it.**
  Light state topics are retained and the bus carries no state broadcast, so on
  restart HA replayed a level from a previous session indistinguishably from a
  live reading — and a switch thrown while the bridge was down was missed for
  good. Observed on the reference coach: 19 of 25 fixtures reported the bridge's
  own start time as their last change, 11 of them claiming `on` while physically
  off. Each fixture now carries a second availability gate and starts
  **unobserved**, clearing itself the first time a command for it is seen, so
  "not known" is distinguishable from "off".

- **Brightness no longer collapses two different levels onto 255.** The light
  discovery template scaled by `* 2.55`, i.e. against 100%, but the decoder
  yields RV-C percent where a fully-on interior fixture reports **125%**. That
  produced 318 for an interior fixture and 255 for a 100% exterior one, both
  clamped by HA to 255. It now scales against `_FULL_SCALE_PCT` — the same
  constant the colour-fixture path already used — so 125% → 255 and 100% → 204.

## [0.3.5] — 2026-07-27

The coach's RV-C device map, rebuilt from the bus rather than from notes. A full
on-bus pass — one narrated press per fixture — found the previous map wrong for
**10 of its 20 entries**: ordered narration had shifted by one position when a
fixture that was already on produced no first-ON transition, and three exterior
*scene buttons* had been published as lights. The same pass established that a
colour fixture is a switch instance plus an R/G/B triplet, which the bridge now
publishes as one Home Assistant entity apiece.

Migrating to a corrected map turned out to need real tooling, built across three
fixes here: HA restores entity_ids from a deleted-entity cache, applies
`suggested_area` only at first creation, and permutes ids when rooms change.

Per-coach data also leaves the repo in this release: the instance map, dashboard,
automations and energy-prefs entity ids are now supplied by the operator's own
inventory and mounted by path, with `*.example.*` counterparts shipped as the
defaults. Still listen-only; the transmit path stays gated (#128).

### Fixed

- **`rename_entities.py` handles re-mapped rooms and id rotations** (#160). Correcting an
  instance map moves fixtures between rooms and permutes their ids, and neither case worked:
  the tool repaired only *missing* device areas, so a fixture re-mapped to another room kept
  the room it was first filed under (HA never re-applies `suggested_area` to an existing
  device) and derived a wrong entity_id from it; and it refused outright when a target id was
  held by another entity that was itself moving. It now repairs wrong areas as well as absent
  ones, and resolves rotations by parking every affected entity on a temporary id before
  releasing any — one at a time collides mid-cycle. A target held by an entity that is *not*
  moving is still a hard refusal. Found by deploying the corrected coach map, which permuted
  seven ids.

### Added

- **RGB colour fixtures** (#122). A Firefly colour fixture is four consecutive
  `DC_DIMMER_COMMAND_2` instances — a switch plus its red/green/blue channels — and the
  bridge now publishes each as **one** Home Assistant entity using the JSON light schema
  rather than four opaque dimmers. State is assembled from all four instances; a colour
  command expands back into up to four writes. `rgb_fixtures` in the instance map gains
  `command_instance` + `channels`, and entries missing either are skipped so an unmapped
  fixture can sit in the map as a placeholder. `handle_command` now returns a *list* of
  frames, since one HA command can be several bus writes.

- **`config/homeassistant/rename_entities.py`** — moves RV-C entity_ids onto the names
  the coach instance map gives them, through HA's entity registry. Needed because
  `--reset-discovery` alone does not move them: HA keeps a `deleted_entities` record
  keyed by `unique_id` and restores the *old* entity_id when that unique_id reappears,
  so entities come back under their previous names however many times discovery is
  republished. Targets are derived from HA's own area/device/entity registries rather
  than a second copy of the map, so the tool cannot drift out of sync with it. Dry-run by
  default; `--show` audits what every RV-C entity resolves to; `--apply` performs the
  moves, refusing outright on a target-id collision.

  Device areas are repaired first, from the retained discovery payloads on the broker
  (#156). HA applies `suggested_area` only when it *first* creates a device, so devices
  restored from `deleted_devices` after a reset come back area-less if they were first
  registered before the map named their zone — and since the area is part of the
  generated entity_id, renaming without repairing it yields `sensor.mid_ac_*` where the
  map means `sensor.galley_mid_ac_*`.

### Fixed

- **Corrected the v0.3.4 rename procedure** in ADR-012 and the coach runbook, which
  claimed a discovery reset was sufficient on its own. Verified on the coach during the
  v0.3.4 deploy: after a clean reset the lights re-registered as
  `light.living_room_living_room_ceiling_living_room_ceiling` with `original_name: None`
  — the new payload had applied, but HA restored the id from its deleted-entity cache.
  The runbook now documents the two-step reset-then-rename, and that a reset only
  rebuilds what the bus re-announces: on a sleeping coach bus, sensor devices stay
  missing until it next wakes (the deploy went from 690 entities to 257 for this reason;
  retained `rvc/state/#` topics are preserved, so values return with the entities).

## [0.3.4] — 2026-07-27

The coach node's observability and operator surface, filled in. Home Assistant
gains a rebuilt six-view dashboard covering what the bridge actually publishes —
lights, interior climate, the AquaHot, and the RV-C side of the AC power system —
and the entity naming behind it is corrected, which needed a supported way to
retire stale discovery. Off the coach, WAN monitoring and long-term metric
storage on the GPU node close the gap left by coach-node's eMMC retention, and the last
UNKNOWN DGNs from the July captures are recognized, so the bus now decodes clean.
Still listen-only; the transmit path stays gated (#128).

### Added

- **Coach dashboards rebuilt on live entities** (#151). The curated HA dashboard gains
  **Home**, **Lights** and **Climate** views and a much deeper **Power** view: the 20
  mapped light fixtures by area, interior temperatures, cooling zones and AC units, the
  AquaHot (water temperature, burner, element, circulation pump), transfer-switch
  qualification, inverter legs, charger state, generator, and the four AC load channels.
  Its System view no longer points at a bench-sim light that no longer exists.

- **`astro-rvc-bridge --reset-discovery`** clears this coach's retained HA discovery and
  exits, so renaming a fixture or zone actually takes effect. HA assigns an entity_id at
  first registration and keeps it even when the name changes; clearing the retained
  config deletes the device and its entities so the next start re-registers them under
  current names. Replaces the manual `mosquitto_pub -r -n` cleanup the v0.3.3 deploy
  needed.

- **Long-term metrics on the GPU node.** `vmagent` on the coach now scrapes every target
  and fans samples out to **both** the local store and a new VictoriaMetrics instance on
  gpu-node (`deploy/gpu/quadlet/coach-metrics-lt.container`). coach-node's rootfs is eMMC, so its
  local retention drops from 24 months to 1 and history lives on gpu-node's NVMe.
  Because gpu-node is the sheddable load when boondocking, the two destinations get
  **independent queues** — an gpu-node outage backs up only its own queue while local
  monitoring continues — and the queue is **capped at 512 MB** so it cannot fill the card
  it exists to protect (~85 days of outage tolerance at current volumes).

- **Coach WAN monitoring.** VictoriaMetrics now scrapes `coach-router`'s node_exporter
  (`192.0.2.1:9100`), and a provisioned Grafana dashboard **"Coach WAN & Segments"**
  graphs metered-cellular usage, gateway up/down, latency, loss, per-WAN and per-VLAN
  throughput, and interface errors. Gateway-quality panels are fed by the
  `coach-gw-metrics` poller on coach-node and stay empty until it is scheduled.

- **Gateway-quality poller in the repo.** `deploy/coach/bin/coach-gw-metrics.py` (plus
  systemd user units in `deploy/coach/systemd/`) polls the router's dpinger results over
  the OPNsense API — authenticating as a dedicated account holding only
  `page-system-gateways` — and pushes `coach_gateway_{delay_ms,stddev_ms,loss_ratio,up}`
  into VictoriaMetrics. Previously it lived only on the deployed node. Install steps:
  `docs/runbooks/coach-node-provisioning.md` §7 (note `loginctl enable-linger`, without
  which the timer silently dies at logout).

- **RV-C decode gaps closed** (#123): the 14 remaining UNKNOWN DGN kinds from the
  2026-07-21 coach captures (~49k frames, the last ~10%) are now recognized. None were
  standard RV-C DGNs missing from the vendored table — all are vendor-proprietary
  (J1939 Proprietary-B PGNs and manufacturer DGNs), so they are classified `internal`
  in `rvc-supplement.yml`: recognized and suppressed rather than logged as UNKNOWN, which
  restores clean-decode soak evidence for the TX-enable gate (ADR-014). Includes
  `DC_DIMMER_CHANNEL_STATUS` (15FCE) — the lighting controller's per-channel state, whose
  channel space still needs the RGB on-bus reconcile (#122) before it can be promoted to
  published `data`. The real-capture fixture is extended to cover every newly-classified
  DGN and now decodes with zero UNKNOWN frames.

### Changed

- **Per-coach data now lives with the deployment, not in this repo.** The instance map,
  curated dashboard, automations and energy-prefs entity ids are mounted via
  `RVC_INSTANCE_MAP`, `HA_DASHBOARD`, `HA_AUTOMATIONS`, `HA_PACKAGES` and
  `ASTROCYTE_ENERGY_PREFS`; this repo ships `*.example.*` counterparts which are also the
  compose defaults, so a fresh checkout still starts. HA's `time_zone` now reads
  `!env_var TZ` — it had drifted to a value that existed only on the deployed node and was
  tracked nowhere.

### Fixed

- **Doubled light entity names** (#151). Light discovery published the fixture name as
  both the device name and the entity name, which HA renders as "Living Room Ceiling
  Living Room Ceiling" and turns into
  `light.living_room_living_room_ceiling_living_room_ceiling`. A single-entity device now
  publishes `"name": null` (omitting the key falls back to "MQTT LightEntity" — verified
  on a live HA 2026.6), and because HA prefixes the device's area into the entity_id,
  coach-map names are area-relative: `Ceiling` in area `Bedroom` → `light.bedroom_ceiling`.
  `THERMOSTAT_AMBIENT_STATUS` also picks up the map's zone names — it is the same zone.
  **Deploy step:** run `--reset-discovery` before restarting the bridge, or HA keeps the
  old ids and the dashboard's light cards stay empty.

- **cadvisor port collisions.** cadvisor moves from `:8080` (UniFi's inform port) to
  `:8081` everywhere — compose, the VictoriaMetrics scrape target, and homepage — and
  Nextcloud's host port moves to `:8082` so enabling the `apps` profile can no longer
  collide with cadvisor. Deploy note: VictoriaMetrics reloads its scrape config only on
  restart, not `SIGHUP`; a stale in-memory config left the cadvisor target down for 13 h.

- **npm audit highs in web dev tooling.** GHSA-mh99-v99m-4gvg (brace-expansion DoS,
  patched only in 5.0.8) reached eslint through minimatch@3, so the old
  `brace-expansion@^1.1.16` override became vulnerable itself; replaced with overrides
  forcing `minimatch@^10` + `brace-expansion@^5.0.8` across the tree (eslint verified
  working against minimatch 10). Also bumps postcss past GHSA-r28c-9q8g-f849.

## [0.3.3] — 2026-07-23

A same-day follow-up from the coach's first **on-bus reconcile session**, which
found that this coach's `DC_DIMMER_STATUS_1` is inert — it broadcasts a fixed
config pattern every ~2 minutes and never reflects live light state. HA lights
are re-based on the signal that does work, `DC_DIMMER_COMMAND_2` (the wall
switches broadcast it on every toggle), keyed on the validated per-fixture
instance map. Still listen-only; the transmit path stays gated.

### Changed

- **RV-C lights are now built from `DC_DIMMER_COMMAND_2`, not `DC_DIMMER_STATUS_1`**
  (#122): the 2026-07-23 on-bus session found this coach's STATUS_1 broadcasts a
  fixed config pattern and never reflects live light state. HA lights are now
  built from the coach instance map keyed on each fixture's command instance
  (named + area'd), with state tracked from observed command traffic and control
  on the same instance — no second instance space, no translation. Discovery for
  all mapped lights publishes at bridge startup and on HA birth. `DC_DIMMER_STATUS_1`
  is reclassified `internal` so its 36 static-config instances stay out of HA.
  The map's command instances were re-validated live (18/20 exact). ADR-012 amended.

## [0.3.2] — 2026-07-23

This release deepens RV-C decode fidelity from the coach's first real-bus
captures (2026-07-21) — all **listen-only**, no actuation change. The decoder now
recognizes the J1939 protocol layer and the high-volume Firefly module↔module
node-sync, so real coach traffic decodes cleanly instead of drowning in
`UNKNOWN`; a per-coach instance map turns bare `Light <n>` entities into named,
area-placed Home Assistant devices and adds a safety guard that refuses to
transmit a light command through an unproven instance mapping. It also ships the
`astro-rvc-analyze` capture toolbox and commits a real-capture test fixture with
byte-exact command-encoder validation — the offline groundwork the future
TX-enable gate (#128) depends on.

### Added

- **Real-capture RV-C test fixture + encoder validation** (#91): a trimmed slice
  of the 2026-07-21 live-bus capture (`tests/fixtures/rvc/coach-reference-20260721.log`)
  with golden decode checks on real coach telemetry and a coverage assertion that
  the whole slice classifies cleanly (only the still-to-decode `15FCE` is
  allowlisted). Confirms our command encoder reproduces the coach's own
  `DC_DIMMER_COMMAND_2` frames byte-exact — the offline half of the TX-enable
  gate (ADR-014). The synthetic fixture and its tests are left untouched.
- **Classify Firefly node-sync DGNs** (#123): the supplement now recognizes the
  proprietary Firefly module↔module sync PGNs (`16F00`/`16300`/`16E00`/`16C00`,
  addressed to nodes 0x92/0x8E) as `internal` — the bulk of the remaining
  UNKNOWN frames (~32.7k in the 2026-07-21 walk-through). Keyed by
  destination-cleared base PGN, so one entry covers every destination.
- **RV-C instance→device naming + safe light-command translation** (#122): a
  coach instance map (`deploy/coach/config/rvc-instances.yml`, schema v1) the
  bridge loads to publish HA friendly names and `suggested_area` instead of bare
  `Light <n>`, and to translate an HA light's `DC_DIMMER_STATUS_1` instance to
  the `DC_DIMMER_COMMAND_2` instance the coach actually listens on. The two
  spaces differ, so a light with no **proven** `status_instance` is left
  bare-numbered and its commands are dropped rather than sent to a guessed
  instance — a hard prerequisite for enabling TX. Entity `object_id`/`unique_id`
  are unchanged, so naming applies in place with no HA duplicates.
- **`astro-rvc-analyze` capture-analysis CLI** (#123): an offline toolbox for
  reverse-engineering the coach's RV-C bus from `candump -L` logs — `summarize`
  (DGN histogram by decode category/source), `correlate` (per-instance first-ON
  timeline, the fixture-naming method from #122), `clusters` (channels that fire
  together, for RGB fixtures), `tp` (J1939 BAM multipacket reassembly), `slice`
  (trim a representative per-DGN test fixture), and `verify-encoder` (diff our
  command encoding against observed touchscreen frames — the offline half of the
  TX-enable gate). Every subcommand is a pure function under the CLI, unit tested
  without a live bus.
- **RV-C decode categories + J1939 protocol recognition** (#123): a local
  `rvc-supplement.yml` (merged over the untouched vendored table) classifies each
  DGN as `data`, `protocol`, or `internal`. The bridge publishes only `data`;
  recognized J1939 plumbing (transport protocol, address claim, request, ACK) and
  Firefly node-sync chatter are counted and suppressed instead of logged as
  `UNKNOWN`. The decoder resolves PDU1 (addressed) frames by their
  destination-cleared PGN and records `destination_address`. Per-category decode
  counters provide the clean-decode soak evidence the TX-enable gate needs.
  ADR-012 amended.
- **AI development governance** (#6): `AI_STRATEGY.md` and `CLAUDE.md` establish
  how AI-assisted development works in this repo, drawing the line between
  development personas (`.github/agents/`) and runtime product agents
  (`src/astrocyte/agents/`). Ships the `finisher` and `scanner` personas and the
  `/pickup-issue`, `/triage-issue`, and `/explain-strategy` commands, mirrored
  into `.claude/` by symlink. The full runtime-persona and skill library, and the
  automated scan→record→fix loop, are deferred to a follow-up.

## [0.3.1] — 2026-07-21

This release brings **time-series observability** to the coach node: energy
telemetry from the Victron system now flows through Home Assistant into
VictoriaMetrics and is graphed in Grafana, with a Homepage portal serving as the
node's front door. It also hardens the deploy path — fixing the image and
Compose issues that surfaced bringing the physical coach online, and turning the
long-red coach-sim E2E green again. All observability services are opt-in
(`--profile observability` / `--profile portal`) and bind loopback only, so the
default coach stack is unchanged.

### Added

- **Observability stack** (`--profile observability`, #117): VictoriaMetrics as
  the time-series store with cAdvisor, node-exporter, and Grafana (provisioned
  **Coach Energy** and **System Health** dashboards). The API now exposes
  `/metrics` (request rate/latency), and Home Assistant's `prometheus:` exporter
  feeds the Victron battery/solar/tank telemetry in. Implements #33 with
  VictoriaMetrics — the TSDB revisit ADR-012 deferred (#94); ADR-012 amended.
- **Homepage portal** (`--profile portal`, #117): the coach node's front-door
  link aggregator with live Home Assistant, Grafana, and Docker widgets.
- Coach actuation policy and tank-level alerts derived from a live bus pull
  (#115).

### Fixed

- Bundle `msgpack` in the image so python-can's `udp_multicast` sim bus works —
  the cause of the long-red coach-sim E2E — and create `/app/state` owned by the
  runtime user so the API can open its approvals database on a fresh volume
  (#116).
- Unbreak `docker compose --profile sim` interpolation: observability-only
  variables no longer hard-fail the sim / E2E path (#118).
- Wire the tank alerts to the live Cerbo GX entity ids, drop the spurious LPG
  alert (AquaHot coach, no propane), and mount `automations.yaml` into Home
  Assistant so its configuration loads cleanly (#119).
- Floor `nltk` to >=3.10.0 to clear CVE-2026-54293 (HIGH) (#114).

### Dependencies

- Routine Dependabot bumps across Python, web, GitHub Actions, and Docker
  (including the base image python 3.12 → 3.14) (#43–#56, #102, #113).

## [0.3.0] — 2026-07-02

The first release: the RV coach node. The reference coach is the
reference deployment for Astrocyte 1.0 (ADR-010); this release carries
everything the coach's always-on node runs, plus the Phase-0 foundation
(scaffold, CI/CD, project management) that preceded it.

### Added

- RV reference-deployment architecture (ADR-010…ADR-014): the reference coach
  becomes the Astrocyte 1.0 reference deployment — Home Assistant as the
  hardware abstraction layer, RV-C telemetry via a SocketCAN→MQTT bridge,
  multi-node topology (coach Pi / GPU workstation / VPS Headscale) with model
  routing, and a tiered agent-actuation safety policy.
- PM restructure per ADR-010: new `v0.3 — RV coach node` milestone (Ops Agent
  → v0.4, RAG → v0.5, renamed in place via new milestone `from:` support in
  `scripts/project-sync.sh`); new `component:rvc` / `component:ha` /
  `rv-deployment` labels with labeler routing.
- `astrocyte.core`: actuation policy engine with tiered rules, rate limits,
  two-phase persisted approvals and a JSONL audit log (ADR-014); `ModelRouter`
  with health-probe fallback across coach/GPU nodes (ADR-013); `DataConnector`
  ABC; `/v1/approvals` API + `aios approve`.
- `astrocyte.rvc`: typed RV-C decoder/encoder over the vendored community
  spec table (Apache-2.0, see NOTICE), and the `astro-rvc-bridge` SocketCAN↔
  MQTT daemon with HA device discovery, listen-only default, and an HA-birth
  discovery replay; vcan-based integration job in CI (ADR-012).
- `astrocyte.ha`: Home Assistant client (REST + WebSocket statistics), the
  first shipped MCP server (`/mcp/ha`) with the policy-gated `call_service`
  write tool and approval mirroring into HA notifications, the first real
  `DataConnector`, and `aios rv status` (ADR-011).
- `astrocyte.agents.coach`: the CoachAgent agents-over-MCP vertical slice —
  LlamaIndex FunctionAgent over the HA MCP tools with ModelRouter-selected
  Ollama providers; `aios rv ask "<question>"`.
- `deploy/`: coach (HA + Mosquitto + Postgres + rvc-bridge + API, with
  `sim`/`local-llm`/`apps` profiles incl. NextCloud), gpu (Ollama on the
  RTX 5080), and vps (Headscale) compose stacks; multi-arch (amd64+arm64)
  release images with an arm64 CI canary; nightly coach-sim e2e workflow.
- Runbooks for the physical install path: coach node provisioning, RV-C CAN
  tap (listen-only + gated TX enablement), GX Tank 140 fuel monitoring, GPU
  node setup, and the Headscale VPS (ADR-010).

- Phase 0 foundational scaffold: `src/astrocyte` Python package (FastAPI app
  factory with `/health` and `/ready`, `aios` CLI stub, agent/MCP placeholders).
- `web/` frontend scaffold (React 19 + Vite + TypeScript) with ESLint, Prettier,
  and Vitest.
- CI/CD: lint, type-check, test (+PR coverage comment), web checks, Docker build,
  and dependency/image security scanning; release workflow publishing images to
  GHCR on tags.
- Tooling: uv project + lockfile, ruff, mypy (strict), pre-commit, Dependabot,
  a `Makefile` task runner, and editor/attribute config.
- Docs: ADR-008 (dev tooling & CI/CD) and `docs/development.md`.
- Project management: declarative `.github/project.yml` reconciled by
  `scripts/project-sync.sh` and a `project-sync` workflow; `component:*` labels
  with path-based auto-routing (`labeler`); release milestones (v0.2–v1.0);
  Epic/Feature/Task/Spike/Bug issue-form templates; PM docs
  (`docs/project-management.md`, `.github/labels.md`, project-setup runbook) and
  ADR-009; full triage of the existing backlog onto the "Astrocyte 1.0" board.

[Unreleased]: https://github.com/astrocyte-project/astrocyte/compare/v0.3.5...HEAD
[0.3.5]: https://github.com/astrocyte-project/astrocyte/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/astrocyte-project/astrocyte/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/astrocyte-project/astrocyte/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/astrocyte-project/astrocyte/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/astrocyte-project/astrocyte/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/astrocyte-project/astrocyte/releases/tag/v0.3.0
