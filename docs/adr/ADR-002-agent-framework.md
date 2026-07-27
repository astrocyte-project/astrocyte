# ADR-002: Agent Framework Selection

## Status

Accepted

## Context

Astrocyte requires an agent framework that can power intelligent operations across multiple domains:

1. **Ops Agent**: Deploy, manage, and heal containerized applications
2. **RAG Agent**: Ingest documents and answer semantic queries
3. **Backup Agent**: Create and restore system snapshots

The framework must support:
- Natural language understanding and intent parsing
- Tool integration and execution
- RAG (Retrieval-Augmented Generation) pipelines
- Structured output generation
- Integration with local LLMs

The framework should be Python-based to align with the broader ecosystem and enable seamless integration with other Python components.

## Decision

We will use **Python + LlamaIndex** as the agent framework for Astrocyte.

### Implementation Details

- **Core Framework**: LlamaIndex for RAG and agent capabilities
- **Language**: Python 3.12+
- **Integration Pattern**: FastMCP for MCP server implementation
- **LLM Integration**: Ollama for local model execution
- **Tool Framework**: LlamaIndex tools and custom Python functions

### Agent Architecture

Each agent will be implemented as:
- A Python class inheriting from LlamaIndex base classes
- MCP server interface using FastMCP
- Tool definitions for specific operations
- Integration with shared services (vector DB, LLM runtime)

## Consequences

### Positive Consequences

- **RAG-Native**: Built-in retrieval and synthesis capabilities
- **Tool Integration**: Seamless tool calling and execution
- **Python Ecosystem**: Rich libraries and community support
- **MCP Compatibility**: Direct integration with MCP protocol
- **Local LLM Support**: Optimized for local model execution

### Negative Consequences

- **Python Dependency**: All agents must be Python-based
- **Learning Curve**: LlamaIndex-specific patterns and APIs
- **Resource Usage**: Python runtime overhead
- **Version Compatibility**: Dependency management complexity

### Risks and Mitigations

- **Risk**: LlamaIndex API changes
- **Mitigation**: Pin major versions and plan migration strategies

- **Risk**: Performance overhead
- **Mitigation**: Profile and optimize critical paths

## Alternatives Considered

### LangChain

**Description**: Comprehensive framework for LLM applications with agents, chains, and tools.

**Pros**:
- Largest ecosystem and community
- Extensive integrations
- Production battle-tested
- Rich agent and chain abstractions

**Cons**:
- Complex API surface
- Heavy dependencies
- Steeper learning curve
- More opinionated architecture

**Why Not Chosen**: LlamaIndex provides better RAG primitives and cleaner abstractions for our use case.

### Autogen

**Description**: Microsoft Research framework for multi-agent conversations and tool use.

**Pros**:
- Multi-agent native support
- Strong conversation patterns
- Research-backed algorithms
- Active Microsoft development

**Cons**:
- Newer and less mature
- Limited RAG capabilities
- Microsoft ecosystem focus
- Less flexible for custom integrations

**Why Not Chosen**: LlamaIndex provides better RAG capabilities and more mature tooling.

### Custom Framework

**Description**: Build a custom agent framework tailored to Astrocyte's needs.

**Pros**:
- Perfect fit for requirements
- Full control over architecture
- No external dependencies
- Optimized for use case

**Cons**:
- High development cost
- Maintenance burden
- Slower time to market
- Limited community support

**Why Not Chosen**: Would significantly delay project timeline and increase maintenance overhead.

### Pure FastMCP

**Description**: Use only FastMCP for MCP server implementation without a higher-level framework.

**Pros**:
- Minimal dependencies
- Direct MCP protocol support
- Lightweight and fast
- Full control over implementation

**Cons**:
- No built-in agent capabilities
- Manual RAG implementation
- More boilerplate code
- Limited high-level abstractions

**Why Not Chosen**: Would require reimplementing RAG and agent patterns from scratch.

## Related Decisions

- ADR-003: Vector Database (LlamaIndex integrates with ChromaDB)
- ADR-004: Local LLM Runtime (LlamaIndex uses Ollama)
- ADR-007: MCP-First Architecture (FastMCP provides MCP server foundation)

## Notes

LlamaIndex will be used primarily for its RAG capabilities and agent abstractions. The Ops Agent may use simpler patterns, while the RAG Agent will leverage LlamaIndex's full feature set. FastMCP will provide the MCP server interface for all agents.
