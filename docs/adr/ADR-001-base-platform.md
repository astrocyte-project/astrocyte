# ADR-001: Base Platform Decision

## Status

Accepted

## Context

Astrocyte needs a container orchestration platform that balances ease of deployment for self-hosters with the ability to manage complex multi-service applications. The platform must support:

- Easy installation on commodity hardware (Debian/Ubuntu servers)
- Service discovery and networking between containers
- Volume management for persistent data
- Resource constraints and health monitoring
- Backup and restore capabilities

The target audience consists of self-hosters who are comfortable with Linux but don't want to manage Kubernetes clusters. They need a solution that "just works" while still being powerful enough for complex applications.

## Decision

We will use **Docker Compose on Debian 12** as the base platform for Astrocyte.

### Implementation Details

- **Base OS**: Debian 12 (stable, LTS, widely supported)
- **Container Runtime**: Docker Engine with Docker Compose v2
- **Service Management**: Docker Compose for multi-service orchestration
- **Networking**: Docker networks with service discovery
- **Volumes**: Named Docker volumes for persistent data
- **Health Checks**: Docker Compose healthcheck directives

### Key Components

- Core services run as Docker containers
- Reverse proxy (Caddy) for external access
- Database services (PostgreSQL) for application data
- Monitoring stack (Prometheus/Grafana) for observability

## Consequences

### Positive Consequences

- **Ease of Deployment**: Simple `docker compose up` commands
- **Familiarity**: Most self-hosters already know Docker
- **Resource Efficiency**: No Kubernetes control plane overhead
- **Development Speed**: Faster iteration cycles
- **Ecosystem**: Rich ecosystem of pre-built images

### Negative Consequences

- **Scaling Limitations**: Not designed for large-scale deployments
- **Manual Operations**: No automatic scaling or self-healing
- **Single Host**: No built-in high availability
- **Upgrade Complexity**: Manual service updates required

### Risks and Mitigations

- **Risk**: Single points of failure
- **Mitigation**: Comprehensive backup strategy (Phase 3)

- **Risk**: Manual scaling becomes burdensome
- **Mitigation**: Documented scaling procedures and migration path to K3s

## Alternatives Considered

### K3s (Lightweight Kubernetes)

**Description**: Single-binary Kubernetes distribution optimized for edge computing.

**Pros**:
- Automatic scaling and self-healing
- Declarative configuration
- Rich ecosystem and tooling
- Production-grade reliability

**Cons**:
- Steeper learning curve for self-hosters
- Higher resource overhead
- More complex deployment and maintenance
- Overkill for single-server deployments

**Why Not Chosen**: Target audience prioritizes simplicity over advanced orchestration features.

### Podman with Quadlet

**Description**: Daemonless container engine with systemd integration.

**Pros**:
- No daemon required
- Native systemd integration
- Rootless operation possible
- Compatible with Docker Compose

**Cons**:
- Smaller ecosystem
- Less mature tooling
- Limited Windows/macOS development support

**Why Not Chosen**: Docker's ecosystem maturity and widespread adoption provide better long-term support.

### Custom Linux Distribution

**Description**: Build a custom OS image with Astrocyte pre-installed.

**Pros**:
- Optimized for the specific use case
- Integrated system management
- Appliance-like experience

**Cons**:
- High development and maintenance cost
- Limited hardware compatibility
- Security update complexity

**Why Not Chosen**: Would significantly increase project scope and complexity.

## Related Decisions

- ADR-005: Zero-Trust Networking (builds on Docker networking)
- ADR-006: API Framework (services run as Docker containers)
- ADR-013: Multi-Node Topology (extends the compose model to coach/gpu/vps
  node classes under `deploy/`)

## Notes

This decision can be revisited if the project grows to require multi-node deployments or advanced orchestration features. The architecture supports migration to K3s through docker-compose-to-k8s conversion tools.
