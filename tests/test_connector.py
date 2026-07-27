"""DataConnector contract tests (seeds #34)."""

from collections.abc import AsyncIterator

import pytest

from astrocyte.core.connector import DataConnector, Document


class FakeConnector(DataConnector):
    connector_id = "fake"

    async def fetch(self) -> AsyncIterator[Document]:
        yield Document(doc_id="1", text="hello", source="fake://1")
        yield Document(
            doc_id="2", text="world", source="fake://2", metadata={"lang": "en"}
        )


def test_abstract_cannot_instantiate() -> None:
    with pytest.raises(TypeError):
        DataConnector()  # type: ignore[abstract]


@pytest.mark.anyio
async def test_fetch_yields_documents() -> None:
    connector = FakeConnector()
    docs = [doc async for doc in connector.fetch()]
    assert [d.doc_id for d in docs] == ["1", "2"]
    assert docs[1].metadata == {"lang": "en"}


@pytest.mark.anyio
async def test_default_discover() -> None:
    assert await FakeConnector().discover() == {"connector_id": "fake"}
