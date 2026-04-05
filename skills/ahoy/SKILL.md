---
name: ahoy
description: "AHOY Orchestrator — Full lifecycle (Planner → Generator → Evaluator loop) of the AI coding harness."
argument-hint: "[project request]"
model: opus
effort: max
---

# AHOY — Agent Harness for Orchestrated Yielding

Run the full lifecycle of the AI coding harness with a single input.

## Usage

- `/ahoy <project request>` — Start a new harness
- `/ahoy` — Resume an interrupted harness

$ARGUMENTS

## Flow

```
Start/Resume → Check state (.claude/harness/harness_state.json)
  None       → Initialize → /ahoy:ahoy-plan
  SPRINTING  → Sprint loop based on current status:
    planned    → Show contract, ask user confirmation
    contracted → Spawn /ahoy:ahoy-gen (Agent tool)
    generated  → Spawn /ahoy:ahoy-eval (Agent tool)
    passed     → Next sprint
    failed     → Rework (attempt < max_attempts) or ask user
    skipped    → Next sprint
    rework     → Re-spawn /ahoy:ahoy-gen (rework mode)
  All done   → Completion report
```

## Output Rules

At every phase transition, explain to the user: **current state**, **what's happening next**, and **why**.
Show a sprint progress table at each loop entry. Keep it concise — no rigid templates.

## 1. Start New Harness

1. Create `.claude/harness/` directory
2. Spawn Planner sub-agent with `/ahoy:ahoy-plan` content
3. Present first sprint contract for user confirmation

## 2. Resume Existing Harness

1. Read `.claude/harness/harness_state.json`
2. If handoff exists in `handoffs/`, read it
3. Execute next step from current state

## 3. Sprint Loop

### Contract Confirmation (planned → contracted)
Show contract.md and ask: "Proceed?", "Modifications needed?", "Skip?"

### Generator (contracted → generated)
Spawn Generator sub-agent via Agent tool with `/ahoy:ahoy-gen` skill content.
After completion, update status to `generated`.

### Evaluator (generated → passed/failed)
Spawn Evaluator sub-agent via Agent tool with `/ahoy:ahoy-eval` skill content.
**Context separation required**: pass only sprint path and project root. Never include Generator conversation history.
Based on verdict, update status to `passed` or `failed`.

### Rework (failed → rework → generated)
1. Increment `attempt` in harness_state.json
2. If attempt < max_attempts (default 3): set status to `rework`, re-call Generator
   - For attempt >= 2: read previous issues.json.attempt-N files and include avoidance context in prompt
3. If attempt >= max_attempts: ask user ("Continue?", "Skip?", "Abort?")

### Sprint Complete → Next Sprint
Increment current_sprint_index, show progress, move to next contract confirmation.

## 4. Context Reset

Every 3 completed sprints or when files exceed 50:
1. Generate handoff: `.claude/harness/handoffs/handoff-NNN.md`
2. Inform user to continue in new session with `/ahoy`

## 5. Completion

Set phase to `complete`, output summary with per-sprint results.

## Enforced Rules (via hooks)

- Cannot pass a sprint without external evaluation (eval_dispatch.py)
- Cannot run Generator without contract.md
- Generator and Evaluator must be separate Agents (context separation)
