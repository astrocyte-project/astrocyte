# ADR-003: Vector Database Choice

## Status

Accepted

## Context

Astrocyte requires a vector database to power semantic search across all user data. The system must support:

- **Document Ingestion**: Store embeddings from multiple data sources
- **Semantic Search**: Find relevant documents based on meaning, not keywords
- **Metadata Filtering**: Filter results by source, date, or other attributes
- **Scalability**: Handle growing document collections
- **Backup Integration**: Include vector data in system backups

The database must work with LlamaIndex and support local deployment without external cloud dependencies.

## Decision

We will use **ChromaDB in embedded mode** as the primary vector database, with a documented migration path to **Weaviate** for larger deployments.

### Implementation Details

- **Primary Database**: ChromaDB embedded (file-based, zero-config)
- **Migration Target**: Weaviate (for scale > 100K documents)
- **Integration**: LlamaIndex vector store abstraction
- **Backup**: Include ChromaDB data directory in snapshots
- **Collections**: Separate collections per app/data source

### Architecture

```
LlamaIndex → ChromaDB Client → Local ChromaDB Instance
                      ↓
               File-based Storage
```

### Migration Strategy

When scaling requirements are met:
1. Deploy Weaviate container
2. Use ChromaDB export tools to migrate data
3. Update configuration to use Weaviate
4. Test and validate migration

## Consequences

### Positive Consequences

- **Zero Configuration**: Embedded mode requires no setup
- **Local Operation**: No cloud dependencies or API keys
- **LlamaIndex Integration**: Native support in agent framework
- **Active Development**: Regular updates and community support
- **Migration Path**: Clear upgrade strategy documented

### Negative Consequences

- **Scaling Limits**: Embedded mode has performance limits
- **Memory Usage**: Loads entire index into memory
- **Backup Complexity**: Large binary files in snapshots
- **Migration Effort**: Manual process to upgrade to Weaviate

### Risks and Mitigations

- **Risk**: Performance degradation with large datasets
- **Mitigation**: Monitor usage and plan migration when approaching limits

- **Risk**: Migration complexity
- **Mitigation**: Document migration process and provide tooling

## Alternatives Considered

### Weaviate (Primary Choice)

**Description**: Open-source vector database with advanced features and scaling capabilities.

**Pros**:
- Production-ready scaling
- Advanced querying and filtering
- RESTful API and client libraries
- Active community and commercial support

**Cons**:
- More complex deployment
- Higher resource requirements
- Steeper learning curve

**Why Not Chosen**: Overkill for initial deployment; ChromaDB embedded meets Phase 1-2 requirements.

### Pinecone

**Description**: Cloud-native vector database service.

**Pros**:
- Managed service (no operations)
- High performance and scalability
- Advanced features (metadata filtering, namespaces)

**Cons**:
- Cloud dependency (not self-hosted)
- API costs for large datasets
- Vendor lock-in concerns

**Why Not Chosen**: Violates self-hosted principle; requires internet connectivity.

### Qdrant

**Description**: Vector similarity search engine with advanced features.

**Pros**:
- High performance
- Rich filtering capabilities
- REST and gRPC APIs
- Active development

**Cons**:
- Newer project (less mature)
- Smaller community
- Less LlamaIndex integration

**Why Not Chosen**: ChromaDB has better LlamaIndex integration and proven stability.

### FAISS (Facebook AI Similarity Search)

**Description**: Library for efficient similarity search and clustering.

**Pros**:
- High performance
- No server required
- Proven in production

**Cons**:
- Library, not database (no persistence, querying)
- Manual index management
- Limited metadata support

**Why Not Chosen**: Requires too much custom infrastructure; not a complete database solution.

### Milvus

**Description**: Cloud-native vector database for scalable similarity search.

**Pros**:
- High scalability
- Advanced features
- Multiple index types

**Cons**:
- Complex deployment
- High resource requirements
- Steep learning curve

**Why Not Chosen**: Too heavy for initial implementation; ChromaDB embedded is sufficient.

## Related Decisions

- ADR-002: Agent Framework (LlamaIndex integration requirement)
- ADR-016: ChromaDB Integration (implementation details)
- ADR-024: Backup Engine (vector data backup requirements)

## Notes

ChromaDB embedded mode will be used for Phase 1-2 development. The system will monitor usage metrics and alert when approaching scaling limits. Migration to Weaviate will be a Phase 3 enhancement with automated tooling.

Performance benchmarks:
- Up to 100K documents: ChromaDB embedded acceptable
- 100K-1M documents: Consider Weaviate migration
- >1M documents: Evaluate distributed solutions
