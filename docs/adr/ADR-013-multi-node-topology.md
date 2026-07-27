# ADR-013: Multi-Node Topology and Model Routing

## Status

Accepted

## Context

The RV reference deployment (ADR-010) is not a single box:

- A **Raspberry Pi 5 (8 GB, arm64)** is the always-on coach node — it must run
  the telemetry and control plane 24/7 within a hard power budget (the house
  bank is 900 Ah; every watt matters while boondocking).
- An **i9 workstation with an RTX 5080 (Linux, x86_64)** travels in the coach
  but is powered on only when in use (~100 W idle, ~700 W under load through
  an inverter leg). It is the only node capable of serious LLM inference.
- Coach internet is **Starlink + cellular** — both CGNAT'd, both intermittent.
  Home and coach must not depend on each other being reachable.

ADR-004 chose Ollama as the LLM runtime and ADR-005 chose Headscale/Tailscale
for zero-trust networking, but neither pinned where the control plane lives or
how agents pick an inference target when the capable node may be off.

## Decision

### Three node classes on one Headscale tailnet

| Node | Hardware | Role | Availability |
|------|----------|------|--------------|
| **coach** | Pi 5, arm64, Raspberry Pi OS Lite + Docker | HA, Mosquitto, PostgreSQL, rvc-bridge, Astrocyte API; optional small Ollama model (`local-llm` compose profile) | always-on |
| **gpu** | i9 + RTX 5080, x86_64 Linux | Ollama with large models (NVIDIA container runtime) | on-demand |
| **vps** | small cloud VM | Headscale control plane + DERP relay | always-on |

- **Headscale runs on the VPS** so coach and home are peers: neither losing
  power or connectivity strands the other's coordination. DERP relaying
  traverses Starlink/cellular CGNAT.
- `tailscaled` runs **on the host** (not as a sidecar) on coach and gpu nodes —
  the HA container and the socketcan bridge already require host networking,
  and host-level tailscale gives every service the tailnet address.
- The Astrocyte API binds to the **tailnet interface**, never `0.0.0.0` on the
  coach LAN (interim exposure control until the Caddy/OAuth2 layer of ADR-005
  is built; see ADR-014).

### Model routing: `ModelRouter`

`astrocyte.core.llm.ModelRouter` selects an inference provider per request
from a declarative registry (`models.yml`): each provider has a priority,
capability tags (e.g. `chat`, `heavy`), an endpoint, and a health probe.
Routing walks providers in priority order and uses the first healthy one;
probe results are cached briefly so a powered-off GPU node costs one timeout,
not one per call.

Degradation ladder on the coach:

1. **gpu node reachable** → large model on the RTX 5080.
2. **gpu off, `local-llm` profile enabled** → small model on the Pi (slow;
   acceptable for short tool-calling turns).
3. **neither** → the call fails fast with a typed error; callers surface
   "AI unavailable until the workstation is powered on." A queued-task mode
   for heavy jobs is a documented follow-up, not part of this ADR.

## Consequences

### Positive Consequences

- **Offline-first**: telemetry, control, dashboards, and alerting never depend
  on internet or the GPU node; only heavy AI does.
- **Power-aware**: the always-on draw is a Pi, not a workstation; the ~700 W
  node runs only when its owner is already using it.
- **Symmetric remote access**: owner devices, coach, home, and VPS are one
  tailnet; no port forwarding anywhere (ADR-005's promise, made concrete).
- **Explicit degradation**: agents know which capability tier they got and can
  adjust behavior rather than silently stalling.

### Negative Consequences

- **VPS dependency + cost**: a (small) always-on cloud bill; Headscale
  outages degrade *new* connections (existing tunnels persist).
- **Three provisioning surfaces**: coach, gpu, and vps each need a runbook.
- **arm64 + x86_64**: images must be multi-arch (CI builds both).

### Risks and Mitigations

- **Risk**: probe caching routes to a GPU node that just powered off.
- **Mitigation**: short cache TTL + per-request fallback on connection error.

- **Risk**: VPS compromise (it sees coordination metadata, not payloads).
- **Mitigation**: Headscale ACLs restrict node-to-node reachability;
  WireGuard payloads are end-to-end encrypted; the VPS relays but cannot read.

## Alternatives Considered

### Everything on the i9 (single powerful node)

**Pros**: simplest; best AI always available.
**Cons**: ~100 W+ continuous draw is untenable off-grid; telemetry dies when
the workstation is off.
**Why Not Chosen**: violates the always-on power budget.

### Headscale at home instead of a VPS

**Pros**: no cloud cost.
**Cons**: home outage strands new coach connections while traveling — the
exact moment remote access matters most.
**Why Not Chosen**: the coach is mobile; the control plane must be neutral.

### Tailscale SaaS instead of Headscale

**Pros**: zero control-plane ops.
**Cons**: contradicts the self-hosted, zero-trust-under-your-control pillar
(ADR-005); adds a third-party dependency for the reference deployment.
**Why Not Chosen**: self-hosting the control plane is the product story.

### Remote inference to a home server / cloud API

**Pros**: no GPU node in the coach.
**Cons**: heavy AI becomes connectivity-dependent (Starlink is intermittent);
cloud APIs contradict local-first AI.
**Why Not Chosen**: the GPU node is already in the coach; local-first wins.

## Related Decisions

- ADR-004: Local LLM Runtime (Ollama — extended here with routing)
- ADR-005: Zero-Trust Networking (Headscale — control-plane placement decided
  here)
- ADR-010: RV Reference Deployment
- ADR-014: Agent Actuation Safety Policy (interim API exposure rules)

## Notes

Node provisioning is documented in `docs/runbooks/coach-node-provisioning.md`,
`docs/runbooks/gpu-node-setup.md`, and `docs/runbooks/vps-headscale.md`.
Compose definitions live under `deploy/{coach,gpu,vps}/`. The heavy-task queue
(run-when-gpu-returns) is tracked as a backlog issue.
