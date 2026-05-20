from __future__ import annotations

from .base import PlatformAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .hermes import HermesAdapter
from .openclaw import OpenClawAdapter
from .opencode import OpenCodeAdapter
from .trae import TraeAdapter


ADAPTERS: dict[str, PlatformAdapter] = {
    "codex": CodexAdapter(),
    "claude": ClaudeAdapter(),
    "trae": TraeAdapter(),
    "opencode": OpenCodeAdapter(),
    "openclaw": OpenClawAdapter(),
    "hermes": HermesAdapter(),
}


def get_adapter(name: str) -> PlatformAdapter:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"unsupported platform: {name}") from exc
