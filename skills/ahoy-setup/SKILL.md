---
name: ahoy-setup
description: "AHOY Setup — Verify prerequisites, diagnose environment issues, and configure external model CLIs for the harness."
argument-hint: ""
model: sonnet
effort: high
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "AskUserQuestion"]
---

# AHOY Setup

Verify that the current environment has everything needed to run AHOY, and guide the user through fixing any issues.

$ARGUMENTS

## Checks to Run

Run all checks below **in parallel where possible** using the Bash tool:

### 1. Python

```bash
python3 --version 2>/dev/null || python --version 2>/dev/null
```

- Required: 3.12+
- If missing: instruct the user to install Python 3.12+

### 2. Doctor diagnostics

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-root "${CLAUDE_PLUGIN_ROOT}" --json \
  || python "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --project-root "${CLAUDE_PLUGIN_ROOT}" --json
```

This runs timeout-safe environment checks from the plugin root and prints a recommendation:
- `blocked`: no authenticated evaluators are usable yet
- `advisory`: one authenticated evaluator (`min_models=1`)
- `strict`: two or more authenticated evaluators (`min_models=2`)

Use the doctor result as the only source of truth for external CLI availability, auth state, and strict-vs-advisory mode. Do not run raw evaluator `--version` probes in setup; the doctor owns those checks with bounded timeouts and separates installed/version/auth/usable states.

### 3. External Model CLIs (doctor-driven recommendation)

- Record CLI state from the doctor JSON fields:
  - `installed`
  - `version_check`
  - `auth_check`
  - `usable_for_eval`
- Use only entries with `usable_for_eval: true` when writing `ahoy_config.json`:
  - `advisory`: 1 usable/authenticated CLI (set `min_models: 1`)
  - `strict`: 2+ usable/authenticated CLIs (set `min_models: 2`)

- In strict mode, consensus is available when 2+ CLIs are usable.

### 4. uv (Python package runner)

```bash
uv --version 2>/dev/null
```

- Required for hook enforcement (`uv run python` in hooks.json)
- If missing: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 5. Plugin installation verification

```bash
echo "${CLAUDE_PLUGIN_ROOT:-NOT_SET}"
```

- If `CLAUDE_PLUGIN_ROOT` is set, plugin is correctly installed
- If not set, user may be running via `--plugin-dir` (still works)

### 6. Validate scripts exist

Check that the following files exist relative to the plugin root:
- `scripts/eval_dispatch.py`
- `scripts/validate_harness.py`
- `hooks/hooks.json`

### 7. Quick validation dry-run

```bash
uv run python "${CLAUDE_PLUGIN_ROOT}/scripts/validate_harness.py" --help 2>/dev/null; echo "exit:$?"
```

## Output Format

Present results as a diagnostic table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## AHOY Environment Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Check               | Status | Details                    |
|---------------------|--------|----------------------------|
| Python              | OK     | 3.12.4                     |
| uv                  | OK     | 0.6.x                     |
| Codex CLI           | OK     | installed                  |
| Gemini CLI          | MISS   | not found                  |
| Claude CLI          | OK     | installed                  |
| Plugin root         | OK     | /path/to/ahoy             |
| eval_dispatch.py    | OK     | found                      |
| validate_harness.py | OK     | found                      |
| hooks.json          | OK     | 7 hooks loaded             |

**Result** examples:

- Advisory: Ready (1/3 external models available) with strict warning
- Strict: Ready (2/3 or more external models available)
```

## After Checks — Auto-Install Phase

After diagnostics, **automatically fix** every issue that can be resolved non-interactively.
Ask the user for confirmation once before starting the batch install, then proceed without further prompts.

### Auto-install flow

1. **Summarize** what will be installed (e.g., "uv, Codex CLI, Gemini CLI를 설치합니다")
2. **AskUserQuestion**: "자동 설치를 진행할까요?" — Yes / No
3. If Yes, run the install commands below **sequentially** (each depends on the previous succeeding):

#### uv (if missing)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env  # or equivalent for the shell
```

#### Codex CLI (if missing)

```bash
npm install -g @openai/codex
```

#### Gemini CLI (if missing)

```bash
npm install -g @google/gemini-cli
```

#### CLAUDE_PLUGIN_ROOT (if not set)

Detect the plugin's actual install path and append the export to the user's shell profile:

```bash
# Find the plugin root (where this SKILL.md lives)
PLUGIN_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]:-$0}")")/../.." && pwd)"
echo "export CLAUDE_PLUGIN_ROOT=\"${PLUGIN_ROOT}\"" >> ~/.bashrc
source ~/.bashrc
```

If `CLAUDE_PLUGIN_ROOT` is already set, skip this step.

### Post-install authentication

After installation, **authentication requires user interaction**. Run the auth commands directly so the user can complete them in-session:

1. **Codex** (if just installed): Tell the user to run `! codex login` to authenticate interactively
2. **Gemini** (if just installed): Tell the user to run `! gemini auth` to authenticate interactively

Explain that the `!` prefix runs the command in the current session so the interactive prompts work.

### Model Selection — Evaluation Config

After install & auth are complete, **ask the user which models to use for evaluation**.

1. Present the list of **installed and authenticated** external model CLIs (e.g., codex, gemini, claude)
2. **AskUserQuestion**: "평가에 사용할 외부 모델을 선택하세요 (추천 모드에 따라 1개 이상 가능)" with options like:
   - Advisory mode (show single-model options):
     - "codex"
     - "gemini"
     - "claude"
   - Strict mode (show combinations):
     - "codex, gemini"
     - "codex, claude"
     - "gemini, claude"
     - "codex, gemini, claude (all)"
   - Only show model combinations that are both installed and authenticated
3. Save the selection to `ahoy_config.json` in the plugin root:

```bash
# Advisory example (min_models = 1)
cat > "${CLAUDE_PLUGIN_ROOT}/ahoy_config.json" <<'CONF'
{
  "eval_models": ["claude"],
  "min_models": 1
}
CONF

# Strict example (consensus mode, min_models = 2)
cat > "${CLAUDE_PLUGIN_ROOT}/ahoy_config.json" <<'CONF'
{
  "eval_models": ["codex", "gemini"],
  "min_models": 2
}
CONF
```
The `eval_models` array determines which models `eval_dispatch.py` calls. The `min_models` value sets the consensus threshold.

If `ahoy_config.json` already exists, read it and show the current config. Ask if the user wants to change it.

### Final re-check

After all installs, auth, and model selection complete, **re-run all diagnostic checks automatically** and present the updated table. Do not ask the user to run `/ahoy:ahoy-setup` again.

### If all checks pass

Tell the user they're ready:
```
Ready to go! Start with:  /ahoy <project request>

Evaluation models: codex, gemini (from ahoy_config.json)
```

### If blockers remain

List only the remaining issues with manual fix instructions. These should only be things that truly cannot be automated (e.g., Python not installed on a system without a package manager, npm not available).
