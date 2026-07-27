# ADR-006: API Framework Selection

## Status

Accepted

## Context

Astrocyte requires a web API framework for service-to-service communication and external integrations. The framework must support:

- **RESTful APIs**: Standard HTTP methods and status codes
- **Authentication**: Integration with OAuth2 and API keys
- **Documentation**: Auto-generated API documentation
- **Validation**: Request/response validation and serialization
- **Performance**: Efficient request handling and response times
- **Security**: Built-in security features and best practices

The framework should be Python-based to align with the agent framework and support both synchronous and asynchronous operations.

## Decision

We will use **FastAPI** as the primary API framework for Astrocyte services.

### Implementation Details

- **Framework**: FastAPI with Python 3.12+
- **ASGI Server**: Uvicorn for production deployment
- **Documentation**: Automatic OpenAPI/Swagger generation
- **Validation**: Pydantic models for request/response schemas
- **Authentication**: FastAPI security utilities with OAuth2
- **Database**: SQLAlchemy with async support

### Service Architecture

Each service will expose:
- REST API endpoints with OpenAPI documentation
- Health check endpoints (/health, /ready)
- Metrics endpoints (/metrics) for monitoring
- Versioned API paths (/v1/)

## Consequences

### Positive Consequences

- **Developer Experience**: Excellent developer tools and documentation
- **Performance**: High performance with async support
- **Type Safety**: Pydantic provides runtime type validation
- **Auto Documentation**: Interactive API documentation
- **Modern Python**: Uses latest Python features and patterns

### Negative Consequences

- **Python Dependency**: All API services must be Python-based
- **Learning Curve**: FastAPI-specific patterns and conventions
- **Async Complexity**: Async programming requires careful handling
- **Resource Usage**: Python runtime overhead

### Risks and Mitigations

- **Risk**: Async programming errors
- **Mitigation**: Code review guidelines and testing requirements

- **Risk**: Performance bottlenecks
- **Mitigation**: Profiling and optimization practices

## Alternatives Considered

### Flask

**Description**: Lightweight WSGI web framework for Python.

**Pros**:
- Simple and flexible
- Large ecosystem of extensions
- Minimal dependencies
- Easy to learn

**Cons**:
- Synchronous by default (async requires additional setup)
- Manual API documentation
- Less built-in validation
- More boilerplate code

**Why Not Chosen**: FastAPI provides better developer experience and modern features.

### Django REST Framework

**Description**: Full-featured REST API framework built on Django.

**Pros**:
- Comprehensive feature set
- Built-in authentication and permissions
- Large community and ecosystem
- Admin interface included

**Cons**:
- Heavy framework with many dependencies
- Synchronous ORM (async support limited)
- Steeper learning curve
- Opinionated architecture

**Why Not Chosen**: Too heavy for microservice architecture; FastAPI more suitable for APIs.

### Starlette

**Description**: ASGI framework focused on building APIs.

**Pros**:
- Lightweight and fast
- Full async support
- Minimal dependencies
- High performance

**Cons**:
- Lower-level framework (more boilerplate)
- Manual validation and documentation
- Less developer-friendly

**Why Not Chosen**: FastAPI builds on Starlette with better high-level features.

### Sanic

**Description**: Async web framework inspired by Flask.

**Pros**:
- High performance async framework
- Flask-like API
- Good for real-time applications
- Active development

**Cons**:
- Smaller community
- Less mature ecosystem
- Manual documentation generation

**Why Not Chosen**: FastAPI has better documentation and validation features.

### Quart

**Description**: Async Flask-like web framework.

**Pros**:
- Flask-compatible API
- Full async support
- Familiar patterns for Flask users

**Cons**:
- Smaller community
- Less mature than FastAPI
- Limited built-in features

**Why Not Chosen**: FastAPI provides more comprehensive API features.

### Express.js

**Description**: Popular Node.js web framework.

**Pros**:
- Large ecosystem and community
- Excellent performance
- Rich middleware ecosystem
- JSON-first design

**Cons**:
- JavaScript/Node.js runtime
- Different language from agent framework
- Additional complexity for polyglot architecture

**Why Not Chosen**: Python alignment with agent framework is preferred.

## Related Decisions

- ADR-002: Agent Framework (Python-based requirement)
- ADR-005: Zero-Trust Networking (authentication integration)
- ADR-007: MCP-First Architecture (API design patterns)

## Notes

FastAPI will be used for all user-facing APIs and internal service APIs. Services will follow RESTful conventions with proper HTTP status codes and content negotiation. API versioning will use URL path versioning (/v1/) to support gradual migration.

Key implementation patterns:
- Dependency injection for database connections
- Middleware for logging and authentication
- Background tasks for async operations
- Streaming responses for large data transfers
