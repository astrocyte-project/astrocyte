# ADR-005: Zero-Trust Networking

## Status

Accepted

## Context

Astrocyte runs multiple services that need secure communication in a self-hosted environment. The networking model must address:

- **Service Isolation**: Prevent unauthorized access between services
- **External Access**: Secure exposure of web interfaces
- **API Security**: Protect internal API endpoints
- **User Authentication**: Identity verification for service access
- **Network Segmentation**: Logical separation of service tiers

The solution must work within Docker Compose architecture and support both internal service-to-service communication and external user access.

## Decision

We will implement **zero-trust networking** using **Caddy as reverse proxy** with **OAuth2 authentication** and **mTLS for service-to-service communication**.

### Implementation Details

- **Reverse Proxy**: Caddy handles all external traffic
- **Authentication**: OAuth2 with multiple providers (Authentik, Keycloak)
- **Service Communication**: mTLS certificates for internal APIs
- **Network Isolation**: Docker networks with service-specific access
- **Certificate Management**: Automated certificate generation and rotation

### Network Architecture

```
Internet → Caddy (TLS, Auth) → Docker Networks
                                    ├── Frontend Network (Web UIs)
                                    ├── API Network (Internal APIs)
                                    └── Data Network (Databases)
```

### Security Controls

- **External Access**: TLS 1.3, OAuth2 authentication
- **Internal Communication**: mTLS with client certificates
- **Network Policies**: Docker network isolation
- **Access Logging**: Comprehensive audit trails

## Consequences

### Positive Consequences

- **Defense in Depth**: Multiple security layers
- **User Experience**: Single sign-on across services
- **Auditability**: Complete access logging and monitoring
- **Scalability**: Architecture supports service growth
- **Industry Standard**: OAuth2 and mTLS are widely adopted

### Negative Consequences

- **Complexity**: More components to manage and configure
- **Certificate Management**: Ongoing certificate lifecycle management
- **Performance Overhead**: TLS termination and authentication add latency
- **User Experience**: Authentication required for all access

### Risks and Mitigations

- **Risk**: Certificate management complexity
- **Mitigation**: Automated certificate generation and renewal

- **Risk**: Authentication failures blocking access
- **Mitigation**: Fallback authentication methods and admin access

## Alternatives Considered

### Basic Reverse Proxy Only

**Description**: Use Caddy or nginx for routing without authentication or mTLS.

**Pros**:
- Simpler implementation
- Lower operational complexity
- Better performance

**Cons**:
- No user authentication
- Plain HTTP internal communication
- Limited security controls

**Why Not Chosen**: Insufficient security for multi-user self-hosted platform.

### VPN-Based Access

**Description**: Require VPN connection for all access to the system.

**Pros**:
- Strong network-level security
- Simple implementation
- Proven technology

**Cons**:
- Poor user experience (VPN setup required)
- Single point of failure (VPN server)
- Limited scalability for multiple users

**Why Not Chosen**: VPN setup creates significant user friction for self-hosters.

### Service Mesh (Istio/Linkerd)

**Description**: Implement a service mesh for advanced traffic management and security.

**Pros**:
- Advanced security features
- Traffic observability
- Automatic mTLS
- Policy enforcement

**Cons**:
- High complexity and resource overhead
- Overkill for Docker Compose deployment
- Steep learning curve

**Why Not Chosen**: Too heavy for initial architecture; may be considered for K3s migration.

### API Gateway Pattern

**Description**: Use an API gateway (Kong, Traefik) for centralized access control.

**Pros**:
- Centralized policy management
- Rich plugin ecosystem
- Good for API-heavy architectures

**Cons**:
- Additional complexity
- May duplicate reverse proxy functionality
- Learning curve for configuration

**Why Not Chosen**: Caddy provides sufficient gateway functionality with simpler deployment.

### Mutual TLS Only

**Description**: Implement mTLS for all communication without OAuth2.

**Pros**:
- Strong cryptographic security
- No user interaction required
- Simple certificate-based access

**Cons**:
- No user identity management
- Difficult to audit user actions
- Complex certificate distribution

**Why Not Chosen**: OAuth2 provides better user experience and audit capabilities.

## Related Decisions

- ADR-001: Base Platform (Docker networking foundation)
- ADR-006: API Framework (authentication integration)
- ADR-008: Identity Management (OAuth2 provider selection)
- ADR-013: Multi-Node Topology (Headscale control plane placed on a VPS;
  host-level tailscaled on coach/gpu nodes)
- ADR-014: Agent Actuation Safety Policy (interim API exposure rules until
  the Caddy/OAuth2 layer lands)

## Notes

Zero-trust networking will be implemented incrementally:

**Phase 1**: Basic reverse proxy with TLS
**Phase 2**: OAuth2 authentication for web interfaces
**Phase 3**: mTLS for service-to-service communication

Certificate management will use automated tools (cert-manager concepts adapted for Docker). The system will provide both user-friendly OAuth2 flows and emergency admin access mechanisms.
