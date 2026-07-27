# ADR-007: MCP-First Architecture

## Status

Accepted

## Context

Astrocyte needs to integrate with external tools and services while maintaining a clean, extensible architecture. The system must support:

- **Tool Integration**: Connect to various external services and APIs
- **Standard Protocols**: Use industry standards for interoperability
- **Security**: Secure communication with external systems
- **Extensibility**: Easy addition of new integrations
- **Agent Communication**: Standardized interface for agent-to-tool communication

The architecture should enable agents to discover and use tools dynamically while maintaining security and reliability.

## Decision

We will adopt an **MCP-first architecture** using the **Model Context Protocol (MCP)** as the primary integration pattern.

### Implementation Details

- **Protocol**: Model Context Protocol for tool integration
- **Server Implementation**: FastMCP for Python-based MCP servers
- **Client Integration**: MCP clients in agent framework
- **Tool Registry**: Centralized registry of available MCP servers
- **Security**: TLS/mTLS for MCP server communication

### Architecture Components

```
Agent Framework (LlamaIndex)
    ↓
MCP Client
    ↓
MCP Server Registry
    ↓
MCP Servers (Tools)
    ├── File System Tools
    ├── Database Tools
    ├── API Integration Tools
    └── Custom Business Logic Tools
```

### MCP Server Categories

- **System Tools**: File operations, process management
- **Data Tools**: Database queries, vector search
- **Integration Tools**: External API calls, webhook handling
- **Utility Tools**: Text processing, data transformation

## Consequences

### Positive Consequences

- **Standardization**: Industry-standard protocol for tool integration
- **Interoperability**: Works with any MCP-compatible tools
- **Security**: Built-in security model for tool access
- **Extensibility**: Easy addition of new tools and integrations
- **Ecosystem**: Growing ecosystem of MCP-compatible tools

### Negative Consequences

- **Protocol Overhead**: Additional abstraction layer
- **Tool Development**: MCP server development required for custom tools
- **Version Compatibility**: MCP specification evolution
- **Debugging Complexity**: Additional debugging layer for tool calls

### Risks and Mitigations

- **Risk**: MCP specification changes
- **Mitigation**: Pin to stable MCP versions and plan migration

- **Risk**: Tool compatibility issues
- **Mitigation**: Comprehensive testing and validation

## Alternatives Considered

### Direct API Integration

**Description**: Agents call external APIs and tools directly.

**Pros**:
- No protocol overhead
- Direct control over integrations
- Simpler debugging
- Maximum flexibility

**Cons**:
- Custom integration code for each tool
- Security concerns with direct access
- Maintenance burden for multiple integrations
- No standardization

**Why Not Chosen**: MCP provides better security, standardization, and maintainability.

### Plugin Architecture

**Description**: Custom plugin system with defined interfaces.

**Pros**:
- Full control over plugin API
- Optimized for specific use case
- No external dependencies
- Flexible plugin loading

**Cons**:
- Custom development and maintenance
- Limited ecosystem
- Integration complexity
- Security implementation required

**Why Not Chosen**: MCP provides industry standard with existing ecosystem.

### REST API Gateway

**Description**: All tools exposed as REST APIs through a gateway.

**Pros**:
- Familiar REST patterns
- Standard HTTP tooling
- Easy testing and debugging
- Broad compatibility

**Cons**:
- No standardized tool calling interface
- Manual API design for each tool
- Authentication and authorization complexity
- Less suitable for agent-driven workflows

**Why Not Chosen**: MCP provides better agent integration and tool discovery.

### gRPC Services

**Description**: Use gRPC for high-performance service communication.

**Pros**:
- High performance and efficiency
- Strong typing with protocol buffers
- Streaming support
- Cross-language support

**Cons**:
- Complex protocol buffer definitions
- Steeper learning curve
- Less web-friendly
- Tool-focused rather than agent-focused

**Why Not Chosen**: MCP provides better agent integration patterns.

### WebSocket Connections

**Description**: Real-time communication via WebSockets.

**Pros**:
- Real-time capabilities
- Bidirectional communication
- Good for interactive tools
- Established web standard

**Cons**:
- Connection management complexity
- Not ideal for stateless operations
- Security concerns with persistent connections
- Limited ecosystem

**Why Not Chosen**: MCP provides better structure for tool operations.

## Related Decisions

- ADR-002: Agent Framework (LlamaIndex MCP integration)
- ADR-005: Zero-Trust Networking (MCP server security)
- ADR-011: Home Assistant as the Hardware Abstraction Layer (the first
  shipped MCP server, `astrocyte.ha.mcp`)
- ADR-014: Agent Actuation Safety Policy (policy enforcement inside MCP
  servers via the `AstrocyteMCP` base class)
- ADR-021: RAG Agent (MCP tool integration)

## Notes

MCP-first architecture will be implemented incrementally:

**Phase 1**: Core MCP server infrastructure
**Phase 2**: Basic tool integrations (file system, databases)
**Phase 3**: Advanced integrations and custom tools

All custom tools will be implemented as MCP servers to maintain consistency. The system will provide both MCP client libraries and server templates to simplify development.

Key benefits:
- **Security**: MCP provides built-in access control
- **Discovery**: Automatic tool discovery and documentation
- **Testing**: Standardized testing patterns for tools
- **Monitoring**: Built-in metrics and logging for tool usage
