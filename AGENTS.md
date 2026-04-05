# Repository Guidelines

## Project Structure & Module Organization
AHOY is a Claude Code plugin. Core metadata lives in `.claude-plugin/plugin.json` and `.mcp.json`. Runtime logic is split between `scripts/` and `hooks/`: `scripts/eval_dispatch.py` dispatches external model evaluation, and `scripts/validate_harness.py` enforces harness state rules. Skill entrypoints live in `skills/` (`ahoy`, `ahoy-plan`, `ahoy-gen`, `ahoy-eval`). Reusable authoring material belongs in `templates/`. User-facing docs live in `README.md`, `docs/README.ko.md`, and `docs/assets/`.

## Build, Test, and Development Commands
This repo does not have a packaged build step. Use these commands during development:

- `python scripts/eval_dispatch.py <sprint_dir> --models codex,claude --project-root .` runs external evaluation for a sprint.
- `python scripts/validate_harness.py guard-eval-files|pre-gen|pre-state-write|post-eval|post-state-write|circuit-breaker` runs individual harness guards.
- `claude --plugin-dir .` loads the plugin locally for manual end-to-end testing.

Use Python 3.10+ as documented in `README.md`.

## Coding Style & Naming Conventions
Follow the existing file style instead of introducing a new one. Python should stay PEP 8–compatible, use type hints where already present, and keep functions small and single-purpose. Keep JSON files pretty-printed with 2-space indentation. Name new skill directories in kebab-case under `skills/`, and keep template files suffixed with `_template.md`.

## Testing Guidelines
Tests live under `tests/` and are run via `uv run pytest`. The suite covers `validate_harness.py` and `eval_dispatch.py` with unit, integration, and end-to-end tests. Coverage threshold is 80% (configured in `pyproject.toml`). When changing `eval_dispatch.py`, verify both successful and failure-path JSON output. When changing `validate_harness.py` or `hooks/hooks.json`, run the relevant guard directly and confirm blocked transitions still fail closed.

## Commit & Pull Request Guidelines
This repository currently has no commit history, so no established commit convention can be inferred yet. Use imperative, scoped commit subjects such as `feat: add gemini retry handling` or `fix: block invalid passed transitions`. PRs should include a short problem statement, the affected paths, manual verification commands, and screenshots only when docs or diagrams change.

## Security & Harness Rules
Do not add code paths that let Claude write `issues.json` directly; that file must remain owned by `eval_dispatch.py`. Preserve the generator/evaluator separation, minimum-two-model consensus, and hook-based fail-closed behavior when extending the plugin.
