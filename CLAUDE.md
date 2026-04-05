# AHOY — Agent Harness for Orchestrated Yielding

Claude Code **plugin** — Generator-Evaluator separation with external model consensus.

## Skills

| Skill | Description |
|-------|-------------|
| **`/ahoy`** | Orchestrator — full lifecycle (entry point) |
| `/ahoy:ahoy-setup` | Setup — verify prerequisites and diagnose environment |
| `/ahoy:ahoy-plan` | Planner — request → spec + sprint contracts |
| `/ahoy:ahoy-gen` | Generator — implements code per contract (Claude) |
| `/ahoy:ahoy-eval` | Evaluator — external model (Codex/Gemini) evaluation dispatch |

## Core Rules

1. **Claude never evaluates** — external models judge Generator output
2. **Contract is truth** — Generator and Evaluator share the same contract.md
3. **File ownership** — issues.json is write-blocked for Claude; only eval_dispatch.py (subprocess) writes it
4. **Consensus required** — minimum 2 valid external models; any fail → final fail
5. **Context reset** — handoff document every 3 sprints

## Sprint State Machine

```
planned → contracted → generated → passed → (next sprint)
   ↓                                  ↑
 skipped                          rework ← failed
```

Sprint object: `{"sprint_id", "title", "status", "attempt": 0, "max_attempts": 3}`

## Hook Enforcement

Hooks in `hooks/hooks.json` use `${CLAUDE_PLUGIN_ROOT}` paths. Key guards:

- **guard-eval-files** — unconditionally blocks Claude from writing issues.json
- **pre-state-write** — requires issues.json + 2 valid models before leaving generated
- **post-state-write** — auto-rollback if `status=passed` but `status_action` is not `passed`
- **pre-gen** — requires contract.md before `ahoy-gen` runs
- **post-eval** — blocks verdict=error/unknown or valid models < 2

## Runtime Notes

- Hook enforcement uses `validate_harness.py`, so Python 3.10+ is required for full enforcement.
- `issues.json` is the source of truth for evaluation. `verdict` explains model consensus; `status_action` tells the orchestrator whether the sprint may move to `passed`.
- **circuit-breaker** — detects repeated failure patterns across rework attempts (runs post-eval)

## Workspace (generated in target project)

```
.claude/harness/
├── harness_state.json
├── spec.md
├── sprints/sprint-NNN/
│   ├── contract.md
│   ├── gen_report.md
│   ├── eval_report.md
│   └── issues.json
└── handoffs/
```
