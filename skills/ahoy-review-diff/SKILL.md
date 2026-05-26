---
name: ahoy:review-diff
description: "AHOY Review Diff — lightweight external review of the current git diff without sprint harness state."
argument-hint: "[--advisory|--strict]"
disable-model-invocation: true
model: opus
effort: max
---

# AHOY Review Diff

Run a lightweight external review of the current `git diff` before opting into the full `/ahoy` sprint harness.

Use this when:
- you want a quick independent review gate for local changes;
- the full sprint/contract state machine is too heavy;
- you need advisory feedback from one evaluator or strict quorum from two or more evaluators.

Do not use this as a replacement for the full `/ahoy` workflow when a sprint contract, rework loop, or persistent acceptance tracking is required.

## Rules

- Review input is `git diff HEAD --` from the current project root.
- Do not create or mutate `.claude/harness/sprints`, `harness_state.json`, or sprint `issues.json`.
- Advisory mode may run with one valid evaluator.
- Strict mode must fail closed unless the configured quorum is available.
- Write a compact report and show the JSON status to the user.

## Procedure

1. Detect mode from arguments:
   - default/advisory: `--mode advisory`
   - strict: `--mode strict`
2. Read models and strict quorum from `ahoy_config.json`.
3. Run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/review_diff.py \
  --project-root . \
  --mode advisory
```

Strict mode:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/review_diff.py \
  --project-root . \
  --mode strict
```

4. Report the result:
   - `no_diff`: tell the user there is no git diff to review.
   - `passed`: summarize report path and reviewer objections.
   - `failed`/`error`: summarize blockers and the report path.

## Output contract

The script prints JSON and writes:

- `ahoy_review_diff_report.md`
- `ahoy_review_diff_report.md.json`

These are local review artifacts only. They are not sprint state.
