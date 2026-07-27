# ADR-010: RV Coach as the Astrocyte 1.0 Reference Deployment

## Status

Accepted

## Context

Astrocyte's roadmap to 1.0 (Epic #2, ADR-009) was defined against an abstract
homelab: Ops Agent and curated apps (v0.3), RAG layer (v0.4), atomic backup and
polish (v1.0). Nothing on that roadmap forced the platform to prove itself
against a real, constrained, physical environment.

A concrete deployment target now exists: a reference coach motor
coach (Freightliner Cascadia chassis) with:

- A **Firefly Integrations Eclipse / G12** multiplex system exposing an
  **RV-C network over CAN bus** (lights, HVAC, tanks, energy management).
- A **Victron Cerbo GX** managing a 900 Ah lithium house bank, with a
  **GX Tank 140** adding engine-off chassis fuel monitoring.
- Intermittent connectivity (Starlink + cellular), a hard power budget, and
  multi-node compute (an always-on Raspberry Pi 5 and an on-demand
  i9/RTX 5080 inference node that travels in the coach).

This environment exercises every Astrocyte pillar harder than a homelab does:
agentic management must respect physical safety; unified search must span live
telemetry; zero-trust networking must survive CGNAT and offline periods; and
backup must cover a system nobody wants to rebuild at a campsite.

## Decision

The RV coach becomes **the reference deployment for Astrocyte 1.0**. Releases
are validated against it, and the roadmap is restructured around what it needs
first:

### Milestone re-sequencing

| Milestone | Theme | Change |
|-----------|-------|--------|
| v0.2 — Foundation & DX | Governance, CI, DX | unchanged |
| **v0.3 — RV coach node: telemetry & safe control** | RV-C bridge, HA integration, actuation policy, multi-node deploy | **new** |
| v0.4 — Ops Agent & curated apps | Ops Agent, `aios` CLI, app registry, zero-trust | renamed from v0.3 |
| v0.5 — RAG layer & unified search | ChromaDB, ingestion, connectors, search | renamed from v0.4 |
| v1.0 — Atomic backup & polish | Backup/restore, AI-verified recovery, **RV reference-deployment validation**, polish | scope extended |

Phase labels (`phase-0..3`) remain the thematic axis and are unchanged; the RV
initiative is tracked with a new **`rv-deployment`** meta label and new
**`component:rvc`** / **`component:ha`** component labels.

### Pragmatic sequencing for curated apps

The v0.3 coach node deploys Home Assistant (ADR-011) and NextCloud via Docker
Compose profiles in a new `deploy/` tree — *before* the Ops Agent and curated
app registry (#7, #10) exist. This is deliberate: the coach needs a working
stack now, and hand-written compose profiles become the first migration
candidates (and acceptance tests) for the registry when it lands in v0.4.
Dogfooding the curated-app pillar is deferred, not abandoned.

### Delivery strategy

The v0.3 work is developed on a single integration branch and lands on `main`
as a stack of reviewable PRs (ADRs/PM → core plumbing → RV-C decoder → bridge →
HA package → agent slice → deploy tree → runbooks), each green under the full
CI gate. Physical installation in the coach follows the runbooks
(`docs/runbooks/rv-*.md`) after the software stack merges; all software is
developed and tested against simulated buses first (ADR-012).

## Consequences

### Positive Consequences

- **Reality check**: every pillar is validated against a physical deployment
  with real sensors, real actuators, and real failure modes.
- **Focus**: "total automation of the coach" is a crisp, demonstrable 1.0
  story, versus an abstract feature list.
- **Early hardware layer**: the platform gains sensor/actuator subsystems and a
  safety-policy engine (ADR-014) that later deployments (homes, labs) reuse.
- **Multi-node story**: the Pi + GPU node + VPS topology (ADR-013) forces
  offline-first, degraded-mode design early.

### Negative Consequences

- **Roadmap churn**: milestones shift by one version; open issues need
  re-milestoning (handled by the declarative PM sync, ADR-009).
- **Ops Agent slips**: agentic app management moves from v0.3 to v0.4.
- **Single-user bias risk**: the reference deployment is one owner's coach;
  generalization must be guarded in code review (nothing coach-specific
  outside config and `deploy/coach/`).

### Risks and Mitigations

- **Risk**: coach-specific assumptions leak into core code.
- **Mitigation**: all coach specifics live in configuration (`policy.yml`,
  `models.yml`, compose env) and `deploy/coach/`; core subsystems stay generic.

- **Risk**: hardware surprises (proprietary Firefly behavior) stall the branch.
- **Mitigation**: everything ships against simulated/recorded data first;
  hardware bring-up is a separate, post-merge step with its own issue.

## Alternatives Considered

### RV as a parallel track, roadmap intact

**Pros**: no milestone churn; existing plan unaffected.
**Cons**: RV work becomes perpetual "side work" with no release pressure; the
platform's 1.0 claims stay unvalidated against real hardware.
**Why Not Chosen**: the owner explicitly wants the coach to *be* the 1.0 test
platform; a parallel track dilutes that.

### RV as a validation environment only

**Pros**: zero process change.
**Cons**: no sensor/actuation subsystems get built at all; "validation" would
be limited to running existing services on a Pi.
**Why Not Chosen**: misses the point — the coach's sensors and controls are the
feature, not just the venue.

## Related Decisions

- ADR-009: GitHub-native Project Management (the declarative spec this
  restructure is expressed in)
- ADR-011: Home Assistant as the Hardware Abstraction Layer
- ADR-012: RV-C Telemetry Architecture
- ADR-013: Multi-Node Topology and Model Routing
- ADR-014: Agent Actuation Safety Policy

## Notes

Coach facts (equipment, wiring, operating baselines) live in the owner's coach
profile document, summarized where needed in `docs/runbooks/rv-*.md`. The
pre-install checklist (coach LAN, Cerbo network access, HA token, remaining
equipment TBDs) is tracked on the RV deployment Epic.
