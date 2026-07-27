"""Agent personas built on LlamaIndex (ADR-002).

``coach`` — the RV CoachAgent, the first agents-over-MCP vertical slice
(ADR-011): HA MCP tools + ModelRouter + actuation policy. The Ops/RAG/Backup
agents land in #7, #21, and #29.

Requires the ``agents`` extra (``pip install astrocyte[agents]``).
"""
