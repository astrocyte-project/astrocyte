# ADR-004: Local LLM Runtime

## Status

Accepted

## Context

Astrocyte requires local LLM execution for privacy, offline operation, and cost control. The runtime must support:

- **Model Compatibility**: Popular open-source models (Llama, Mistral, etc.)
- **GPU Acceleration**: NVIDIA/AMD GPU passthrough for performance
- **API Integration**: REST API for agent framework integration
- **Resource Management**: Memory and compute resource controls
- **Model Management**: Download, update, and switch models

The solution must work in a containerized environment and integrate with the broader Astrocyte architecture.

## Decision

We will use **Ollama** as the local LLM runtime for Astrocyte.

### Implementation Details

- **Runtime**: Ollama server in Docker container
- **Model Storage**: Persistent volume for downloaded models
- **API Integration**: REST API calls from Python agents
- **GPU Support**: NVIDIA Container Toolkit passthrough
- **Model Selection**: Curated set of models for different use cases

### Supported Models

- **Chat/General Purpose**: llama3.2, mistral
- **Embedding**: nomic-embed-text
- **Code Generation**: codellama, deepseek-coder
- **Specialized**: Future additions based on requirements

### Deployment Architecture

```
Docker Compose Service: ollama
├── GPU Passthrough: NVIDIA/AMD
├── Volume: /models (persistent)
├── API Port: 11434
└── Health Check: /api/tags
```

## Consequences

### Positive Consequences

- **GPU Support**: Native GPU acceleration for better performance
- **Model Variety**: Wide range of supported models
- **Simple API**: Clean REST interface for integration
- **Active Development**: Regular updates and new features
- **Container Ready**: Works seamlessly in Docker environments

### Negative Consequences

- **Resource Intensive**: High memory and compute requirements
- **Model Size**: Large downloads for high-quality models
- **Cold Start**: Initial model loading can be slow
- **Limited Customization**: Less flexible than building custom solutions

### Risks and Mitigations

- **Risk**: GPU compatibility issues
- **Mitigation**: Test on common hardware configurations

- **Risk**: Model performance variability
- **Mitigation**: Benchmark and document performance expectations

## Alternatives Considered

### llama.cpp (Direct)

**Description**: Direct execution of GGUF models using llama.cpp library.

**Pros**:
- Maximum customization and control
- No additional runtime overhead
- Direct hardware optimization
- Small binary size

**Cons**:
- Complex integration and management
- Manual model format conversion
- Limited high-level features
- More maintenance overhead

**Why Not Chosen**: Ollama provides better developer experience and ecosystem integration.

### vLLM

**Description**: High-performance LLM serving framework with advanced features.

**Pros**:
- Excellent performance and optimization
- Advanced serving features (batching, quantization)
- Production-ready reliability
- Strong for concurrent requests

**Cons**:
- Higher complexity and resource requirements
- Less model format support
- Steeper operational requirements

**Why Not Chosen**: Overkill for initial requirements; Ollama meets Phase 1-2 needs.

### Text Generation WebUI

**Description**: Feature-rich web interface for running LLMs locally.

**Pros**:
- Rich web interface
- Multiple backend support
- Active community and extensions
- User-friendly for experimentation

**Cons**:
- Web-focused (less API-oriented)
- Complex deployment
- Resource overhead from web interface

**Why Not Chosen**: API-first design better suits agent integration needs.

### LocalAI

**Description**: Self-hosted OpenAI-compatible API for local LLMs.

**Pros**:
- OpenAI API compatibility
- Multiple backend support
- Easy migration from cloud APIs
- Container-ready

**Cons**:
- Additional abstraction layer
- Performance overhead
- Less mature than Ollama

**Why Not Chosen**: Ollama provides better performance and native features.

### LM Studio

**Description**: Desktop application for running LLMs locally.

**Pros**:
- User-friendly interface
- Good performance
- Easy model management

**Cons**:
- Desktop-focused (not server/container)
- Limited API capabilities
- Not suitable for headless deployment

**Why Not Chosen**: Requires GUI environment and not designed for server deployment.

## Related Decisions

- ADR-002: Agent Framework (LlamaIndex integrates with Ollama)
- ADR-013: Multi-Node Topology (ModelRouter selects among Ollama instances
  across nodes with health-probe fallback)
- ADR-016: ChromaDB Integration (embedding models run via Ollama)
- ADR-021: RAG Agent (uses Ollama for response synthesis)

## Notes

Ollama will be deployed as a Docker service with GPU passthrough enabled. Models will be pre-downloaded during initial setup to ensure availability. The system will monitor resource usage and provide guidance for optimal model selection based on available hardware.

Performance expectations:
- **CPU-only**: 2-5 tokens/second (basic usability)
- **GPU-enabled**: 20-50+ tokens/second (good responsiveness)
- **Memory**: 4-16GB RAM depending on model size
