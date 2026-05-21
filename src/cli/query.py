from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..agent import AgentResponse, build_query_request, resolve_provider
from ..mcp.service import LLMWikiService


def register_query(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("query", help="Answer a question from the LLM Wiki through an agent provider.")
    parser.add_argument("question", nargs="+", help="Question to answer from the knowledge base.")
    parser.add_argument("--root", default=".", help="Knowledge base root.")
    parser.add_argument("--provider", choices=["openai", "command"], help="Agent provider. Defaults to env or OpenAI.")
    parser.add_argument("--model", help="Model name for provider=openai. Defaults to LLM_WIKI_MODEL.")
    parser.add_argument("--agent-command", help="External command for provider=command. Reads JSON on stdin and writes JSON on stdout.")
    parser.add_argument("--top", type=int, default=10, help="Search result limit for context gathering.")
    parser.add_argument("--record", action="store_true", help="Record the completed query in log.md.")
    parser.add_argument("--confirm", default="", help="Required write confirmation token for --record: WRITE-KB.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    parser.set_defaults(handler=run_query)


def run_query(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    question = " ".join(args.question).strip()
    if not question:
        raise ValueError("query requires a question")
    request = build_query_request(root, question, top=args.top)
    provider = resolve_provider(args.provider, model=args.model, agent_command=args.agent_command)
    response = provider.complete(request)

    record_result = None
    if args.record:
        service = LLMWikiService(root)
        record_result = service.record_query(
            question=question,
            summary=response.answer[:500],
            themes=[source for source in response.sources if source.startswith("themes/")],
            answer_status=response.answer_status,
            writeback_candidate=response.writeback_candidate,
            writeback_target=response.writeback_target,
            gaps=response.gaps,
            confirm=args.confirm,
        )

    if args.format == "json":
        print(
            json.dumps(
                {
                    "question": question,
                    "response": response.to_dict(),
                    "record": record_result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_response(response)
        if record_result:
            print()
            print(f"record_status: {record_result.get('status')}")
            if record_result.get("error"):
                print(f"record_error: {record_result['error']}")
    return 2 if record_result and record_result.get("status") == "needs_confirmation" else 0


def _print_response(response: AgentResponse) -> None:
    print(response.answer)
    print()
    print(f"answer_status: {response.answer_status}")
    print(f"writeback_candidate: {response.writeback_candidate}")
    if response.writeback_target:
        print(f"writeback_target: {response.writeback_target}")
    if response.sources:
        print("sources:")
        for source in response.sources:
            print(f"- {source}")
    if response.gaps:
        print("gaps:")
        for gap in response.gaps:
            print(f"- {gap}")
