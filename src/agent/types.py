from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ANSWER_STATUSES = {"confirmed", "inferred", "insufficient"}


@dataclass
class ProposedChange:
    path: str
    action: str = "write"
    content: str = ""
    rationale: str = ""
    confidence: str = "tentative"

    @classmethod
    def from_value(cls, value: Any) -> "ProposedChange":
        if isinstance(value, str):
            return cls(path=value)
        if not isinstance(value, dict):
            return cls(path="")
        return cls(
            path=str(value.get("path") or value.get("target") or ""),
            action=str(value.get("action") or "write"),
            content=str(value.get("content") or ""),
            rationale=str(value.get("rationale") or value.get("reason") or ""),
            confidence=str(value.get("confidence") or "tentative"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResponse:
    answer: str
    answer_status: str = "inferred"
    sources: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    writeback_candidate: str = "no"
    writeback_target: str = ""
    proposed_changes: list[ProposedChange] = field(default_factory=list)
    commands_to_run: list[str] = field(default_factory=list)
    raw_text: str = ""
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["proposed_changes"] = [change.to_dict() for change in self.proposed_changes]
        return payload


@dataclass
class AgentRequest:
    operation: str
    root: Path
    task: dict[str, Any]
    instructions: str
    context: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "root": str(self.root),
            "task": self.task,
            "instructions": self.instructions,
            "context": self.context,
            "response_schema": response_schema(),
        }


def response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["answer", "answer_status"],
        "properties": {
            "answer": "string",
            "answer_status": "confirmed|inferred|insufficient",
            "sources": ["path-or-url"],
            "gaps": ["graph_gap|output_gap|evidence_gap|other"],
            "writeback_candidate": "yes|no",
            "writeback_target": "path or empty string",
            "proposed_changes": [
                {
                    "path": "repo-relative KB path",
                    "action": "write|append",
                    "content": "full file content for write, appended text for append",
                    "rationale": "why this change is justified by sources",
                    "confidence": "confirmed|inferred|tentative",
                }
            ],
            "commands_to_run": ["deterministic follow-up commands"],
        },
    }


def parse_agent_response(text: str, *, provider: str = "") -> AgentResponse:
    raw = text.strip()
    payload = _parse_json_object(raw)
    if payload is None:
        return AgentResponse(answer=raw, raw_text=raw, provider=provider)

    answer = str(payload.get("answer") or payload.get("short_answer") or raw)
    answer_status = str(payload.get("answer_status") or "inferred")
    if answer_status not in ANSWER_STATUSES:
        answer_status = "inferred"
    writeback = payload.get("writeback_candidate", "no")
    if isinstance(writeback, bool):
        writeback = "yes" if writeback else "no"
    sources = _string_list(payload.get("sources"))
    gaps = _string_list(payload.get("gaps"))
    commands = _string_list(payload.get("commands_to_run"))
    changes = [ProposedChange.from_value(item) for item in _list(payload.get("proposed_changes"))]
    changes = [change for change in changes if change.path]
    return AgentResponse(
        answer=answer,
        answer_status=answer_status,
        sources=sources,
        gaps=gaps,
        writeback_candidate=str(writeback or "no"),
        writeback_target=str(payload.get("writeback_target") or ""),
        proposed_changes=changes,
        commands_to_run=commands,
        raw_text=raw,
        provider=provider,
    )


def dumps_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _list(value) if str(item).strip()]


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
