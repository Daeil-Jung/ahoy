---
name: ahoy-gen
description: "AHOY Generator — Implements code and tests per sprint contract. No self-evaluation."
disable-model-invocation: true
model: opus
effort: max
---

# Harness Generator

Reads sprint contracts and implements code and tests.
**Does not perform self-evaluation** — verdicts are determined by external models.

## Input

Read from `.claude/harness/harness_state.json`:
- `.claude/harness/sprints/sprint-NNN/contract.md` (required)
- `.claude/harness/spec.md` (overall context)
- `.claude/harness/sprints/sprint-NNN/issues.json` (in rework mode)

## Implementation Rules

- Only create/modify files specified in contract.md "Implementation Scope"
- Never modify "Files to Preserve"
- Follow existing coding style and `.claude/rules/` if present
- Write tests for each AC — must be executable (no stubs/TODOs)

## Rework Mode

If `issues.json` exists:
1. Read issues and use `suggestion` field as primary fix guidance
2. Fix by priority: P0 > P1 > P2 > P3
3. For attempt >= 2: read previous `issues.json.attempt-N` and `gen_report.md.attempt-N` files to avoid repeating failed approaches. Use a fundamentally different strategy.

## Test Execution

After implementation, run `eval_strategy.test_command` from spec.md. Fix failures.

## Output

Write `.claude/harness/sprints/sprint-NNN/gen_report.md`:
```markdown
---
sprint_id: "sprint-NNN"
generated_at: "(ISO 8601)"
attempt: N
---
# Generator Report: sprint-NNN
## Implementation Summary
### Files Created
- `path/to/file`
### Files Modified
- `path/to/file`
## Acceptance Criteria Coverage
| AC | Implementation | Test File | Test Result |
## Test Execution Results
## Out-of-Scope Changes (if any)
## Unresolved Issues (if any)
```

The `### Files Created` and `### Files Modified` sections are required — `eval_dispatch.py` uses them.

Update sprint status to `generated` in `harness_state.json`.

## Prohibited

- Self-verdicts ("this sprint passes")
- Features not in contract.md
- Modifying other sprints' files
- Bypassing tests with skip/mock
- Writing issues.json or eval_report.md
- Judgment language ("satisfied", "pass") in gen_report.md — record only facts
