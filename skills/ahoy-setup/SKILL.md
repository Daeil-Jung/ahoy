---
name: ahoy-setup
description: "AHOY Setup — Verify prerequisites and configure external model CLIs."
argument-hint: ""
model: sonnet
effort: high
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "AskUserQuestion"]
---

# AHOY Setup

Verify environment and guide the user through fixing issues.

$ARGUMENTS

## Checks (run in parallel)

1. **Python**: 3.10+ required
2. **uv**: required for hook enforcement
3. **External Model CLIs** (at least 2): `codex --version`, `gemini --version`, `claude --version`
4. **Plugin root**: `${CLAUDE_PLUGIN_ROOT}` set?
5. **Scripts exist**: `scripts/eval_dispatch.py`, `scripts/validate_harness.py`, `hooks/hooks.json`

Present results as a diagnostic table.

## Auto-Install

After diagnostics, offer to auto-install missing tools:
- uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Codex CLI: `npm install -g @openai/codex`
- Gemini CLI: `npm install -g @google/gemini-cli`

For auth, tell user to run `! codex login` or `! gemini auth` interactively.

## Model Selection

Ask user which models to use for evaluation (minimum 2). Save to `ahoy_config.json`:
```json
{
  "eval_models": ["codex", "gemini"],
  "min_models": 2
}
```

## Final

Re-run checks and confirm readiness: `Ready to go! Start with: /ahoy <project request>`
