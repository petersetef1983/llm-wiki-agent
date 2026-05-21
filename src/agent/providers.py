from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Protocol

from .types import AgentRequest, AgentResponse, dumps_payload, parse_agent_response


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


class AgentProviderError(RuntimeError):
    pass


class AgentProvider(Protocol):
    name: str

    def complete(self, request: AgentRequest) -> AgentResponse:
        ...


class CommandProvider:
    name = "command"

    def __init__(self, command: str, *, timeout: int = 600) -> None:
        if not command.strip():
            raise AgentProviderError("--agent-command or LLM_WIKI_AGENT_COMMAND is required for provider=command")
        self.command = command
        self.timeout = timeout

    def complete(self, request: AgentRequest) -> AgentResponse:
        command = _split_command(self.command)
        proc = subprocess.run(
            command,
            cwd=request.root,
            input=dumps_payload(request.to_payload()),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            raise AgentProviderError(
                f"agent command exited with {proc.returncode}: {(proc.stderr or proc.stdout).strip()}"
            )
        return parse_agent_response(proc.stdout, provider=self.name)


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("LLM_WIKI_MODEL") or DEFAULT_OPENAI_MODEL

    def complete(self, request: AgentRequest) -> AgentResponse:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on optional dependency.
            raise AgentProviderError(
                "OpenAI provider requires the optional dependency: pip install 'llm-wiki-agent[agent]'"
            ) from exc

        client = OpenAI()
        system = (
            "You are the LLM Wiki semantic agent. Return only a JSON object that matches "
            "the provided response_schema. Do not invent sources. Proposed changes must be "
            "grounded in supplied context and include rationale and confidence."
        )
        user = dumps_payload(request.to_payload())
        text = self._complete_with_responses(client, system, user)
        return parse_agent_response(text, provider=self.name)

    def _complete_with_responses(self, client: object, system: str, user: str) -> str:
        responses = getattr(client, "responses", None)
        if responses is not None and hasattr(responses, "create"):
            try:
                response = responses.create(
                    model=self.model,
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                return _response_text(response)
            except (AttributeError, TypeError):
                pass

        chat = getattr(client, "chat", None)
        completions = getattr(chat, "completions", None)
        if completions is None or not hasattr(completions, "create"):
            raise AgentProviderError("installed OpenAI SDK does not expose responses or chat completions APIs")
        response = completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return str(response.choices[0].message.content or "")


def resolve_provider(
    provider: str | None,
    *,
    model: str | None = None,
    agent_command: str | None = None,
) -> AgentProvider:
    selected = (provider or os.environ.get("LLM_WIKI_PROVIDER") or "").strip().lower()
    command = agent_command or os.environ.get("LLM_WIKI_AGENT_COMMAND")
    if not selected:
        selected = "command" if command else "openai"
    if selected == "command":
        return CommandProvider(command or "")
    if selected == "openai":
        return OpenAIProvider(model=model)
    raise AgentProviderError(f"unsupported provider: {selected}")


def _split_command(command: str) -> list[str]:
    if os.name == "nt":
        return [part.strip('"') for part in shlex.split(command, posix=False)]
    return shlex.split(command)


def _response_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    output = getattr(response, "output", None)
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for part in content:
                    text = getattr(part, "text", None)
                    if text:
                        chunks.append(str(text))
        if chunks:
            return "\n".join(chunks)
    return str(response)
