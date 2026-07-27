"""Data connector contract.

The minimal seed of the plugin SDK (#34): a connector turns an external
system's content into ``Document`` objects for the future RAG ingestion
pipeline (#18). The first real implementation is
``astrocyte.ha.HomeAssistantConnector``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Document:
    """One unit of ingestible content."""

    doc_id: str
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DataConnector(ABC):
    """Turns an external system into a stream of documents."""

    #: Stable identifier, e.g. ``"home-assistant"``.
    connector_id: str = ""

    @abstractmethod
    def fetch(self) -> AsyncIterator[Document]:
        """Yield the connector's current documents."""

    async def discover(self) -> dict[str, str]:
        """Human-readable facts about the source (name, version, counts)."""
        return {"connector_id": self.connector_id}
