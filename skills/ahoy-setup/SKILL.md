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

- Required: 3.10+
- If missing: instruct the user to install Python

### 2. External Model CLIs (at least 2 required)

```bash
codex --version 2>/dev/null; echo "exit:$?"
gemini --version 2>/dev/null; echo "exit:$?"
claude --version 2>/dev/null; echo "exit:$?"
```

- Record which CLIs are available
- At least 2 must be present for consensus evaluation

### 3. uv (Python package runner)

```bash
uv --version 2>/dev/null
```

- Required for hook enforcement (`uv run python` in hooks.json)
- If missing: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 4. Plugin installation verification

```bash
echo "${CLAUDE_PLUGIN_ROOT:-NOT_SET}"
```

- If `CLAUDE_PLUGIN_ROOT` is set, plugin is correctly installed
- If not set, user may be running via `--plugin-dir` (still works)

### 5. Validate scripts exist

Check that the following files exist relative to the plugin root:
- `scripts/eval_dispatch.py`
- `scripts/validate_harness.py`
- `hooks/hooks.json`

### 6. Quick validation dry-run

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

**Result**: Ready (2/3 external models available)
```

## After Checks

### If all checks pass
Tell the user they're ready and show how to start:
```
Ready to go! Start with:  /ahoy <project request>
```

### If issues are found
Group issues by severity and provide fix commands:

**Blockers** (cannot run AHOY):
- Missing Python → install instructions per OS
- Missing uv → `pip install uv` or installer URL
- Fewer than 2 external model CLIs → installation links

**Warnings** (can run but limited):
- Only 2 of 3 external models → suggest installing the third
- Old Python version (3.10-3.11) → works but 3.12+ recommended

Provide copy-pasteable fix commands for each issue. After the user fixes issues, suggest running `/ahoy:ahoy-setup` again to re-verify.
