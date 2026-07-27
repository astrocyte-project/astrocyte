"""MCP servers exposing subsystem capabilities as tools.

Per the MCP-first architecture (ADR-007), each subsystem ships a FastMCP
server. ``AstrocyteMCP`` (``server.py``) is the shared, policy-aware base
every server builds on (ADR-014); the first concrete server is the Home
Assistant one (``astrocyte.ha.mcp``, ADR-011). Ops/RAG/Backup servers land in
#15, #23, and #31.

Requires the ``mcp`` extra (``pip install astrocyte[mcp]``).
"""
