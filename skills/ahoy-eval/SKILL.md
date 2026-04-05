---
name: ahoy-eval
description: "AHOY Evaluator — Verifies Generator output using external models. Claude does not make pass/fail verdicts."
disable-model-invocation: true
model: opus
effort: max
---

# Harness Evaluator — External Model Evaluation

**Claude does not perform evaluations.** External models evaluate; Claude only records results.

## Procedure

### 1. Run Tests Directly

Run the `eval_strategy.test_command` from spec.md via Bash.
Always re-verify — do not trust the Generator's reported results.

### 2. External Model Evaluation

Read eval config, then run eval_dispatch.py:

```bash
EVAL_MODELS=$(python3 -c "import json; c=json.load(open('${CLAUDE_PLUGIN_ROOT}/ahoy_config.json')); print(','.join(c['eval_models']))" 2>/dev/null || echo "codex,claude")
MIN_MODELS=$(python3 -c "import json; c=json.load(open('${CLAUDE_PLUGIN_ROOT}/ahoy_config.json')); print(c.get('min_models',2))" 2>/dev/null || echo "2")

python ${CLAUDE_PLUGIN_ROOT}/scripts/eval_dispatch.py \
  .claude/harness/sprints/sprint-NNN \
  --models "${EVAL_MODELS}" \
  --min-models "${MIN_MODELS}" \
  --project-root .
```

This script calls external models in parallel, computes consensus, and writes `issues.json`.

### 3. Read Results and Record

Read `issues.json` and write `eval_report.md`. **Record the verdict as-is — do not modify it.**

eval_report.md format:
```markdown
---
sprint_id: "sprint-NNN"
evaluated_at: "(ISO 8601)"
verdict: "(verdict)"
status_action: "(passed|failed|error)"
evaluated_by: ["codex", "claude"]
---
# Evaluation Report: sprint-NNN
## External Model Results
## Test Execution Results
## Issues Found
## Acceptance Criteria Verification
```

### 4. Status Update

Update sprint status in `harness_state.json` based on `status_action`:
- `"passed"` → status = `passed`
- `"failed"` → status = `failed`
- `"error"` → do not advance; surface the failure

## Prohibited

- Making verdicts without running eval_dispatch.py
- Overriding a fail verdict to pass
- Modifying issues.json
