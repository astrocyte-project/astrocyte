# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the Astrocyte project. ADRs are documents that capture important architectural decisions made during the development of the system.

## What is an ADR?

An ADR is a document that describes a significant architectural decision made for the project. It includes the context, the decision made, and the consequences of that decision.

## ADR Structure

Each ADR follows a standard template and includes:

- **Title**: Clear, descriptive title
- **Status**: Current status (Proposed, Accepted, Deprecated, Superseded)
- **Context**: Background and problem statement
- **Decision**: The decision that was made
- **Consequences**: Positive and negative consequences
- **Alternatives Considered**: Other options that were evaluated

## How to Create a New ADR

1. Copy `template.md` to create a new ADR file
2. Name it using the format `ADR-XXX-title.md` where XXX is the next sequential number
3. Fill in all sections of the template
4. Submit as a pull request for review

## ADR Status Definitions

- **Proposed**: Decision is under consideration
- **Accepted**: Decision has been made and implemented
- **Deprecated**: Decision is no longer recommended but may still be in use
- **Superseded**: Decision has been replaced by a newer ADR

## Review Process

All ADRs must be reviewed and approved by the core development team before being accepted. The review process ensures:

- Decisions align with project goals
- Consequences are properly evaluated
- Alternatives are fairly considered
- Documentation is clear and complete

## Current ADRs

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](ADR-001-base-platform.md) | Base Platform Decision | Accepted | 2026-04-26 |
| [ADR-002](ADR-002-agent-framework.md) | Agent Framework Selection | Accepted | 2026-04-26 |
| [ADR-003](ADR-003-vector-database.md) | Vector Database Choice | Accepted | 2026-04-26 |
| [ADR-004](ADR-004-llm-runtime.md) | Local LLM Runtime | Accepted | 2026-04-26 |
| [ADR-005](ADR-005-zero-trust-networking.md) | Zero-Trust Networking | Accepted | 2026-04-26 |
| [ADR-006](ADR-006-api-framework.md) | API Framework | Accepted | 2026-04-26 |
| [ADR-007](ADR-007-mcp-architecture.md) | MCP-First Architecture | Accepted | 2026-04-26 |
| [ADR-008](ADR-008-dev-tooling-cicd.md) | Development Tooling & CI/CD | Accepted | 2026-06-29 |
| [ADR-009](ADR-009-project-management.md) | GitHub-native Project Management | Accepted | 2026-07-01 |
| [ADR-010](ADR-010-rv-reference-deployment.md) | RV Coach as the 1.0 Reference Deployment | Accepted | 2026-07-02 |
| [ADR-011](ADR-011-home-assistant-hardware-layer.md) | Home Assistant as the Hardware Abstraction Layer | Accepted | 2026-07-02 |
| [ADR-012](ADR-012-rvc-telemetry-architecture.md) | RV-C Telemetry Architecture | Accepted | 2026-07-02 |
| [ADR-013](ADR-013-multi-node-topology.md) | Multi-Node Topology and Model Routing | Accepted | 2026-07-02 |
| [ADR-014](ADR-014-actuation-safety-policy.md) | Agent Actuation Safety Policy | Accepted | 2026-07-02 |

## Contributing

When proposing architectural changes:

1. Check if an existing ADR covers the topic
2. If creating a new ADR, ensure it follows the template
3. Consider the broader impact on the system
4. Document assumptions and constraints clearly

## References

- [ADR Inspiration](https://adr.github.io/) - Original ADR concept
- [Michael Nygard's ADRs](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions) - Original article
- [Spotify ADR Template](https://github.com/spotify/adr-tools) - ADR tooling
