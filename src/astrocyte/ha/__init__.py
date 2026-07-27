"""Home Assistant integration — astrocyte's hardware abstraction layer (ADR-011).

- ``client`` — REST + WebSocket client (long-lived token auth).
- ``connector`` — DataConnector feeding entity snapshots to future RAG (#18).
- ``mcp`` — the HA MCP server, astrocyte's first shipped MCP server; its
  single write tool is gated by the actuation policy (ADR-014).

Requires the ``ha`` extra (``pip install astrocyte[ha]``).
"""

from astrocyte.ha.client import HAAuthError, HAClient, HAError
from astrocyte.ha.connector import HomeAssistantConnector

__all__ = ["HAAuthError", "HAClient", "HAError", "HomeAssistantConnector"]
