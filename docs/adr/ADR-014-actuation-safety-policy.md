# ADR-014: Agent Actuation Safety Policy

## Status

Accepted (amended 2026-07-27 — see [Amendments](#amendments))

## Context

With the RV deployment, Astrocyte agents gain tools that actuate physical
hardware: lights, fans, HVAC setpoints — and, on the same bus, the generator,
energy-management system, and inverters. A wrong or hallucinated tool call is
no longer a bad API response; it can start an engine, shed a load, or drain a
battery bank.

The README's security analysis already demanded fine-grained control over
agent execution permissions. ADR-007 makes MCP servers the tool surface, which
is exactly where enforcement can live. Nothing existing covers: who may call
which tool, which calls need a human, and how any of it is audited.

## Decision

A generic, tiered **actuation policy engine** in `astrocyte.core.policy`,
enforced **inside every MCP server that exposes write tools** — never in the
agent, which cannot be trusted to self-police.

### Tiers

Policy is declarative (`policy.yml`, path from `POLICY_FILE`). Every actuation
request `(domain, service, target)` resolves to a tier:

| Tier | Behavior | RV examples |
|------|----------|-------------|
| `read` | always allowed | entity state, history, statistics |
| `control` | allowed, rate-limited, audited | lights, fans, HVAC setpoints |
| `guarded` | two-phase human confirmation | EMS changes, water heater, anything touching inverters |
| `deny` | refused | **generator start/stop (initially)**, anything unlisted |

**Default-deny**: an action matching no rule is denied. Generator start/stop
stays `deny` — not even human-approved agent actuation — until the RV-C bus
and command encodings are validated on the real coach; only then is it flipped
to `guarded` by a deliberate config change (see the install runbook). The
autonomy end-state (e.g. auto-start on low battery) is a post-validation
backlog item.

### Two-phase approval flow (`guarded`)

1. Agent invokes the tool → policy returns
   `{status: "pending_approval", approval_id, expires}` (with a TTL).
2. A human approves or denies via `aios approve <id>` or
   `POST /v1/approvals/{id}`; pending approvals are also mirrored into Home
   Assistant as persistent notifications (companion app push over the
   tailnet).
3. The agent re-invokes the tool with the confirmation token; tokens are
   single-use and expire with the approval.

Pending approvals are **persisted on disk** (SQLite on a coach volume,
stdlib-only; the trivial schema migrates to the shared PostgreSQL instance
when the application DB layer lands) so an API restart doesn't void a human's
pending decision. The in-memory store is for tests/dev only.

### Rate limits and audit

- **Per-tool rate limits** apply even to `control`-tier actions (a confused
  agent must not cycle lights or HVAC dozens of times a minute).
- Every actuation attempt — allowed, pending, approved, denied, or
  rate-limited — is appended to a JSONL **audit log** with timestamp, tool,
  arguments, tier, decision, and approval linkage.

### Interim API exposure (until ADR-005's proxy exists)

The Caddy/OAuth2/mTLS layer (#11) is not built yet. Until it is:

- the coach API binds to the **tailnet interface only** (never `0.0.0.0` on
  the coach LAN), and
- the MCP mount (`/mcp/ha`) and `/v1/approvals` require a **static bearer
  token** from environment.

The actuation surface is never reachable unauthenticated, even from coach
Wi-Fi guests.

## Consequences

### Positive Consequences

- **Enforcement at the choke point**: every actuator passes one audited gate;
  adding an MCP server cannot accidentally bypass policy if it uses the shared
  base class (`astrocyte.mcp.AstrocyteMCP`).
- **Human-in-the-loop where it matters**, autonomy where it's safe — matching
  the "monitor + safe control" 1.0 scope (ADR-010).
- **Reusable**: the Ops Agent (#7) adopts the same engine for infrastructure
  actions (deploys, restarts, file edits).
- **Auditability**: incident review starts from an append-only record.

### Negative Consequences

- **Friction**: guarded actions need a second round-trip and a human.
- **Policy drift risk**: `policy.yml` must evolve with the entity population;
  default-deny turns omissions into refusals (safe, but occasionally
  annoying).
- **Interim auth is coarse**: one bearer token, no per-principal identity
  until the zero-trust proxy lands.

### Risks and Mitigations

- **Risk**: an MCP server exposes a write tool without policy wrapping.
- **Mitigation**: write tools are registered through the `AstrocyteMCP` base
  class decorator; code review + a test asserting every write tool resolves a
  tier.

- **Risk**: approval fatigue trains the human to rubber-stamp.
- **Mitigation**: keep the `guarded` set small and meaningful; `control` covers
  the routine cases; rate limits bound the blast radius.

## Alternatives Considered

### Agent-side self-restraint (prompting)

**Pros**: no infrastructure.
**Cons**: prompts are not a security boundary; a confused model ignores them.
**Why Not Chosen**: physical actuation demands enforcement, not etiquette.

### RBAC on the API gateway only

**Pros**: standard pattern.
**Cons**: gateway sees HTTP routes, not tool semantics; cannot distinguish
"set thermostat" from "start generator" inside one MCP endpoint; no approval
flow.
**Why Not Chosen**: the decision granularity lives at the tool layer.

### Hardware-level interlocks only

**Pros**: strongest guarantee.
**Cons**: the bridge's listen-only mode (ADR-012) already provides the
hardware-adjacent interlock; alone it is all-or-nothing and can't express
"lights yes, generator no."
**Why Not Chosen**: complementary, not sufficient — both layers are used.

## Amendments

### 2026-07-27 — the RV-C bridge enforces default-deny on its own command path

The tier table above is enforced in `core/policy.py`, which sits on the MCP and
API surfaces. The RV-C bridge's MQTT→CAN path does **not** pass through it, and
that gap was wider than intended.

`RvcBridge.handle_command` gated only on `listen_only`. Its mapped-light branch
is properly constrained — it refuses any instance absent from the coach map —
but its *generic* branch, `rvc/cmd/<dgn_name>/<instance>`, encoded **any command
DGN in the spec** from raw JSON fields. That is 69 DGNs, among them
`GENERATOR_COMMAND`, `GENERATOR_DEMAND_COMMAND`, `SLIDE_COMMAND`,
`LEVELING_CONTROL_COMMAND`, `CHASSIS_MOBILITY_COMMAND`, `LOCK_COMMAND` and
`DC_DISCONNECT_COMMAND`. The broker is anonymous on the node's loopback, so
anything running there could reach it.

Clearing `listen_only` would therefore have exposed generator start/stop —
which this ADR places in `deny`, "not even human-approved agent actuation" — as
a side effect of enabling light control. The default-deny principle was stated
here but not implemented at that layer.

**Decision:** the generic path is now allowlisted by DGN name via
`ASTROCYTE_RVC_COMMAND_ALLOWLIST`, **empty by default**. Enabling TX no longer
implicitly enables it, and refusals are counted (`denied_commands`) and logged.
Mapped-light control keeps its own branch and its own map-membership guard, so
it is unaffected.

This is a floor, not a replacement for the tier engine: it constrains *which
DGNs can be encoded at all*, while `policy.yml` continues to classify actions
into `auto`/`control`/`guarded`/`deny`. Routing bridge commands through the tier
engine remains the fuller answer.

Note also that enabling TX requires **two** independent gates, not one: this
setting, and the host's `can0` unit, which brings the interface up with
`listen-only on` at the driver level. Flipping only the application setting
transmits nothing.

## Related Decisions

- ADR-005: Zero-Trust Networking (the permanent auth story; interim rules here)
- ADR-007: MCP-First Architecture (the enforcement surface)
- ADR-011: Home Assistant as the Hardware Abstraction Layer (the first gated
  server)
- ADR-012: RV-C Telemetry (listen-only default — the layer below this one)

## Notes

The RV `policy.yml` ships in `deploy/coach/config/` with the tier map above.
`policy.yml` classification matches on HA service-call shape
(`domain`, `service`, entity/device targets, with glob support); the engine is
HA-agnostic so other MCP servers can express their own action shapes. Audit
log location defaults to a volume-mounted path on the coach node and is a
backup target (phase-3).
