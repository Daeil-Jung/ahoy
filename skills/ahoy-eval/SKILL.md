---
name: ahoy-eval
description: "AHOY Evaluator — Independently verifies Generator output using external models (Codex, Gemini, etc.). Claude does not make pass/fail verdicts on its own. Called by the orchestrator (/ahoy)."
disable-model-invocation: true
model: opus
effort: max
---

# Harness Evaluator — External Model Evaluation

Independently verifies Generator output using **external models (Codex, Gemini, etc.)**.
Claude does not make pass/fail verdicts on its own.

## Core Principle

**Claude does not perform evaluations.** External models evaluate, and Claude only records the results.
This is to physically block self-evaluation bias.

## User Guidance Output Rules

Provide detailed natural language explanations of each step to the user during the evaluation process.

## Procedure

### 1. Run Tests Directly

Run the `eval_strategy.test_command` from spec.md via Bash.
Even if the Generator reported "passed", always run tests directly to verify.

```bash
# Examples
uv run pytest -v
npm test
go test ./...
```

Output to the user before and after execution:
```
## Direct Test Execution

Independently re-verifying the test results reported by the Generator.
Running tests directly rather than trusting the Generator's report is a core harness principle.

**Command**: uv run pytest -v
```

After execution:
```
**Test result**: 12 passed, 0 failed (3.2s)
**Matches Generator report**: Yes (or "No — Generator reported N passed, actual is M passed")
```

### 2. External Model Evaluation Dispatch

**Run eval_dispatch.py via Bash** to delegate evaluation to external models:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/eval_dispatch.py \
  .claude/harness/sprints/sprint-NNN \
  --models codex,claude \
  --project-root .
```

Output to the user before execution:
```
## External Model Evaluation Dispatch

External models review the code in a process completely separated from the Generator (Claude).
The results of this evaluation cannot be changed by Claude — the external process writes directly to issues.json.

**Models to call**: codex, claude (separate processes)
**Evaluation input**:
  - contract.md (acceptance criteria)
  - gen_report.md (implementation report)
  - Actual code files (up to 20)

**Consensus rule**: Any fail → final fail. Any `partial_pass` → final `partial_pass`.

Running eval_dispatch.py...
```

This script:
- Collects contract.md + gen_report.md + actual code
- Calls Codex CLI and Claude CLI (separate process) respectively
- Calculates consensus of both verdicts
- Saves results to `.claude/harness/sprints/sprint-NNN/issues.json`

**Available model options**:
- `codex` — OpenAI Codex CLI
- `gemini` — Google Gemini CLI
- `claude` — Anthropic Claude CLI (context separated since it's a separate process)

Adjust the `--models` argument to match the installed CLIs.

### 3. Read Results and Record

Read `issues.json` and write `eval_report.md`.

**Claude records the external model's verdict as-is. It does not modify it.**
Treat `status_action` in `issues.json` as the source of truth for whether the sprint may move to `passed`.

After reading results, output to the user:
```
## External Model Evaluation Results: sprint-NNN

**Final verdict: PASS** (or FAIL / PARTIAL_PASS)

### Verdict by Model

| Model | Verdict | Issue Count | Summary |
|-------|---------|-------------|---------|
| codex | pass | 0 | All ACs satisfied |
| claude | pass | 1 (minor) | Minor improvement suggested for AC-003 |

### Acceptance Criteria Verification

| AC | codex | claude | Consensus |
|----|-------|--------|-----------|
| AC-001 | PASS | PASS | PASS |
| AC-002 | PASS | PASS | PASS |
| AC-003 | PASS | PASS (minor issue) | PASS |

(If there are issues)
### Issues Found

| ID | Severity | Category | Found By | Description | Suggested Fix |
|----|----------|----------|----------|-------------|---------------|
| ISS-001 | minor | quality | claude | ... | ... |
```

eval_report.md format:
```markdown
---
sprint_id: "sprint-NNN"
evaluated_at: "(ISO 8601)"
verdict: "(external model consensus verdict)"
status_action: "(passed|failed|error)"
evaluated_by: ["codex", "claude"]
---
# Evaluation Report: sprint-NNN

## External Model Evaluation Results
- Codex verdict: (pass|partial_pass|fail)
- Claude verdict: (pass|partial_pass|fail)
- **Consensus**: (final verdict)
- **Status action**: (passed|failed|error)

## Test Execution Results (Claude direct execution)
(pytest/jest etc. output)

## Issues Found (external model aggregate)
| ISS-ID | Severity | Category | Found By | Description |

## Acceptance Criteria Verification
### PASS: (external models agreed)
### FAIL: (external models agreed)
```

### 4. Status Update

Update the current sprint status in `harness_state.json`:
- `status_action: "passed"` → Set status to `passed`
- `status_action: "failed"` → Set status to `failed`
- `status_action: "error"` → Do not advance; surface the evaluation failure

After status update, output to the user:
```
(If PASS)
**Sprint sprint-NNN passed.** Moving to the next sprint.

(If PARTIAL_PASS — passing because only minor issues)
**Sprint sprint-NNN conditionally passed.** There are N minor issues but no blocker/major issues, so it passes.
Moving to the next sprint. Minor issues are recorded as future improvements.

(If PARTIAL_PASS — failing because blocker/major exist)
**Sprint sprint-NNN failed.** It was a partial_pass but has N blockers and M majors requiring rework.
Starting rework (attempt N/max_attempts).

(If FAIL)
**Sprint sprint-NNN failed.** N blockers and M majors need to be fixed.
Starting rework (attempt N/max_attempts).
```

## Validation Hooks (implemented in hooks)

4 hooks run automatically to enforce harness rules:

1. **PreToolUse** `Write/Edit(*harness_state*)` → `validate_harness.py pre-state-write`
   - issues.json integrity verification (required fields exist, timestamp format)
   - Confirm at least 2 valid models (`models_valid`)
2. **PreToolUse** `Write/Edit(*harness_state*)` → `validate_harness.py post-state-write`
   - Auto-rollback if `status=passed` but `status_action` is not `passed`
3. **PreToolUse** `Bash/Agent(*ahoy-gen*)` → `validate_harness.py pre-gen`
   - Verify contract.md exists
4. **PostToolUse** `Bash(*eval_dispatch*)` → `validate_harness.py post-eval`
   - Block if verdict is error/unknown
   - Block if fewer than 2 valid models

## Prohibited Actions

- X Making verdicts without running eval_dispatch.py
- X Re-verdicting an external model's fail verdict as pass
- X Ignoring issues based on Claude's own judgment of "this is good enough"
- X Modifying external model verdicts in issues.json
