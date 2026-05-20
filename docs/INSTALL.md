# Installation

## pipx

```powershell
pipx install llm-wiki-agent
llm-wiki init --target C:\path\to\my-kb --dry-run
llm-wiki init --target C:\path\to\my-kb --confirm CREATE-KB
```

## uvx

```powershell
uvx llm-wiki-agent init --target C:\path\to\my-kb --dry-run
```

By default `init` enables `codex`, `claude`, `trae`, `opencode`, `openclaw`, and `hermes`. Use `--platform` to generate only a subset.

## Local source checkout

```powershell
python -m src --help
python -m src init --target C:\path\to\my-kb --dry-run
```
