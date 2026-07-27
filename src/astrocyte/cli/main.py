"""Entry point for the ``aios`` console script.

Command set grows with the subsystems: ``approve`` (guarded-actuation
approvals, ADR-014) landed with the RV deployment; the broader command set
(deploy/stop/start/restart/status/logs/chat) lands in #9.
"""

import argparse
import asyncio
import json
from collections.abc import Sequence

import httpx

from astrocyte import __version__
from astrocyte.core.config import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aios",
        description="Astrocyte — Self-Hosted AI Operating System CLI.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    approve = subparsers.add_parser(
        "approve",
        help="List or resolve pending guarded-actuation approvals (ADR-014).",
    )
    approve.add_argument(
        "approval_id",
        nargs="?",
        help="Approval to resolve; omit to list pending approvals.",
    )
    approve.add_argument(
        "--deny",
        action="store_true",
        help="Deny instead of approve.",
    )

    rv = subparsers.add_parser("rv", help="Coach status and queries (ADR-011).")
    rv_sub = rv.add_subparsers(dest="rv_command")
    rv_sub.add_parser(
        "status",
        help="One-call coach snapshot from Home Assistant (battery/fuel/tanks).",
    )
    ask = rv_sub.add_parser(
        "ask",
        help="Ask the CoachAgent a question (LLM over the HA MCP tools).",
    )
    ask.add_argument("question", help="Natural-language question about the coach.")
    return parser


def _api_client() -> httpx.Client:
    settings = get_settings()
    headers = (
        {"Authorization": f"Bearer {settings.api_token}"} if settings.api_token else {}
    )
    return httpx.Client(base_url=settings.api_url, headers=headers, timeout=10.0)


def _cmd_approve(approval_id: str | None, deny: bool) -> int:
    with _api_client() as client:
        if approval_id is None:
            response = client.get("/v1/approvals")
            response.raise_for_status()
            pending = response.json()
            if not pending:
                print("No pending approvals.")
                return 0
            for item in pending:
                targets = ",".join(item["targets"]) or "-"
                print(
                    f"{item['approval_id']}  {item['domain']}.{item['service']}"
                    f"  targets={targets}"
                )
            return 0
        response = client.post(
            f"/v1/approvals/{approval_id}", json={"approve": not deny}
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            print(f"Unknown approval: {approval_id}")
            return 1
        response.raise_for_status()
        item = response.json()
        print(f"{item['approval_id']} -> {item['status']}")
        return 0


def _cmd_rv_status() -> int:
    settings = get_settings()
    if not settings.ha_token:
        print("ASTROCYTE_HA_TOKEN is not set; cannot reach Home Assistant.")
        return 1
    try:
        from astrocyte.ha.client import HAClient
        from astrocyte.ha.status import collect_rv_status
    except ImportError:
        print("The 'ha' extra is not installed (pip install astrocyte[ha]).")
        return 1

    async def snapshot() -> dict[str, object]:
        client = HAClient(settings.ha_url, settings.ha_token)
        try:
            return collect_rv_status(await client.get_states())
        finally:
            await client.aclose()

    print(json.dumps(asyncio.run(snapshot()), indent=2, sort_keys=True))
    return 0


def _cmd_rv_ask(question: str) -> int:
    settings = get_settings()
    if not settings.ha_token:
        print("ASTROCYTE_HA_TOKEN is not set; cannot reach Home Assistant.")
        return 1
    try:
        from astrocyte.agents.coach import build_coach_agent
        from astrocyte.core.llm import NoProviderAvailableError
    except ImportError:
        print(
            "The 'agents' extras are not installed "
            "(pip install astrocyte[agents,ha,mcp])."
        )
        return 1
    agent = build_coach_agent()
    try:
        print(asyncio.run(agent.ask(question)))
    except NoProviderAvailableError as exc:
        print(f"AI unavailable: {exc}")
        print("Power on the GPU workstation or enable the local-llm profile.")
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "approve":
        return _cmd_approve(args.approval_id, args.deny)
    if args.command == "rv" and getattr(args, "rv_command", None) == "status":
        return _cmd_rv_status()
    if args.command == "rv" and getattr(args, "rv_command", None) == "ask":
        return _cmd_rv_ask(args.question)
    # No subcommand (or bare `rv`): show help so the CLI is self-describing.
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
