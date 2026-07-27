"""CoachAgent — the agents-over-MCP vertical slice (ADR-002/ADR-011/ADR-013).

A LlamaIndex agent whose tools are the HA MCP server's tools, invoked through
an in-memory FastMCP client so every actuation still passes the policy engine
(ADR-014), and whose LLM is resolved per-question by the ModelRouter — the
GPU workstation when it's powered, the coach model otherwise.

The tool wrappers are declared as typed Python functions (mirroring
``astrocyte.ha.mcp``) so the LLM gets clean parameter schemas.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastmcp import Client

from astrocyte.core.llm import ModelRouter, ResolvedProvider
from astrocyte.mcp.server import AstrocyteMCP

SYSTEM_PROMPT = """You are the coach agent for a reference coach motor \
home. You observe and (within policy) control the coach through Home Assistant \
tools. Facts about this coach: 900 Ah lithium house bank, dual 3000 W \
inverters on a split-leg 120V system, Onan 12.5 kW generator sharing the \
120-gal diesel tank (loses prime below ~30%).

Rules:
- Ground every answer in tool results; never invent sensor values.
- call_service may return pending_approval: tell the user to run \
`aios approve <approval_id>`, then retry with approval_token once approved.
- A denied result is final. Do not retry denied actions or look for \
workarounds.
"""


def _dump(data: Any) -> str:
    return data if isinstance(data, str) else json.dumps(data, default=str)


def build_coach_tools(mcp: AstrocyteMCP) -> list[Any]:
    """LlamaIndex FunctionTools that proxy the HA MCP server's tools."""
    from llama_index.core.tools import FunctionTool

    async def _call(tool: str, arguments: dict[str, Any]) -> str:
        async with Client(mcp.server) as client:
            result = await client.call_tool(tool, arguments)
        return _dump(result.data)

    async def rv_status() -> str:
        """One-call coach snapshot: battery, fuel, tanks, climate, power."""
        return await _call("rv_status", {})

    async def list_entities(
        domain: str | None = None, pattern: str | None = None
    ) -> str:
        """List Home Assistant entities, filtered by domain and/or id glob."""
        arguments: dict[str, Any] = {}
        if domain is not None:
            arguments["domain"] = domain
        if pattern is not None:
            arguments["pattern"] = pattern
        return await _call("list_entities", arguments)

    async def get_state(entity_id: str) -> str:
        """Full state (with attributes) of one entity."""
        return await _call("get_state", {"entity_id": entity_id})

    async def get_history(entity_id: str, start: str, end: str | None = None) -> str:
        """Raw state history for one entity (ISO-8601 timestamps)."""
        arguments: dict[str, Any] = {"entity_id": entity_id, "start": start}
        if end is not None:
            arguments["end"] = end
        return await _call("get_history", arguments)

    async def get_statistics(
        statistic_ids: list[str],
        start: str,
        end: str | None = None,
        period: str = "hour",
    ) -> str:
        """Long-term aggregates — the right tool for trend questions."""
        arguments: dict[str, Any] = {
            "statistic_ids": statistic_ids,
            "start": start,
            "period": period,
        }
        if end is not None:
            arguments["end"] = end
        return await _call("get_statistics", arguments)

    async def call_service(
        domain: str,
        service: str,
        entity_ids: list[str] | None = None,
        data: dict[str, Any] | None = None,
        approval_token: str | None = None,
    ) -> str:
        """Actuate via Home Assistant. Policy-gated; see the approval rules."""
        arguments: dict[str, Any] = {"domain": domain, "service": service}
        if entity_ids is not None:
            arguments["entity_ids"] = entity_ids
        if data is not None:
            arguments["data"] = data
        if approval_token is not None:
            arguments["approval_token"] = approval_token
        return await _call("call_service", arguments)

    return [
        FunctionTool.from_defaults(async_fn=fn)
        for fn in (
            rv_status,
            list_entities,
            get_state,
            get_history,
            get_statistics,
            call_service,
        )
    ]


def default_agent_factory(provider: ResolvedProvider, tools: list[Any]) -> Any:
    """A LlamaIndex FunctionAgent on the routed Ollama provider."""
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.llms.ollama import Ollama

    llm = Ollama(
        model=provider.model, base_url=provider.endpoint, request_timeout=120.0
    )
    return FunctionAgent(tools=tools, llm=llm, system_prompt=SYSTEM_PROMPT)


def build_coach_agent() -> CoachAgent:
    """Assemble a CoachAgent from process settings (used by ``aios rv ask``).

    Uses the same policy/approvals wiring as the API service; with
    ``ASTROCYTE_APPROVALS_DB`` set, approvals created here are visible to
    ``aios approve`` and the API.
    """
    from astrocyte.core.config import get_settings
    from astrocyte.core.llm.router import ProviderSpec
    from astrocyte.core.policy import (
        AuditLog,
        InMemoryApprovalStore,
        PolicyEngine,
        SqliteApprovalStore,
    )
    from astrocyte.ha.client import HAClient
    from astrocyte.ha.mcp import build_ha_mcp

    settings = get_settings()
    store = (
        SqliteApprovalStore(settings.approvals_db)
        if settings.approvals_db is not None
        else InMemoryApprovalStore()
    )
    audit = AuditLog(settings.audit_log)
    if settings.policy_file is not None:
        policy = PolicyEngine.from_file(settings.policy_file, store=store, audit=audit)
    else:
        policy = PolicyEngine(store=store, audit=audit)  # default deny-all
    mcp = build_ha_mcp(HAClient(settings.ha_url, settings.ha_token), policy)
    if settings.models_file is not None:
        router = ModelRouter.from_file(settings.models_file)
    else:
        router = ModelRouter(
            providers=(
                ProviderSpec(
                    name="local",
                    endpoint="http://localhost:11434",
                    model="llama3.2:3b",
                ),
            )
        )
    return CoachAgent(mcp, router)


class CoachAgent:
    """Answers questions about (and safely operates) the coach."""

    def __init__(
        self,
        mcp: AstrocyteMCP,
        router: ModelRouter,
        *,
        agent_factory: Callable[[ResolvedProvider, list[Any]], Any] | None = None,
    ) -> None:
        self.mcp = mcp
        self.router = router
        self._agent_factory = agent_factory or default_agent_factory
        self._tools: list[Any] | None = None

    @property
    def tools(self) -> list[Any]:
        if self._tools is None:
            self._tools = build_coach_tools(self.mcp)
        return self._tools

    async def ask(self, question: str) -> str:
        """Route to a healthy model, run the agent, return its answer."""
        provider = await self.router.route("chat")
        agent = self._agent_factory(provider, self.tools)
        result = await agent.run(question)
        return str(result)
