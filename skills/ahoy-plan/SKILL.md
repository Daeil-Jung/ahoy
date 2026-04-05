---
name: ahoy-plan
description: "AHOY Planner — Converts user requests into spec.md and sprint contracts."
disable-model-invocation: true
argument-hint: "[project request]"
model: opus
effort: max
---

# Harness Planner

Converts user prompts into a project spec and sprint contracts.

## Input

$ARGUMENTS

## Procedure

### 1. Tech Stack Detection
Scan project root: `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `CLAUDE.md`.
If empty project, ask user via AskUserQuestion.

### 2. Feature Decomposition
- Assign FEAT-ID to each feature
- Specify dependencies
- Write **verifiable** acceptance criteria (not vague like "implement user management")
- Ambiguous requirements → AskUserQuestion

### 3. Sprint Organization
1 sprint = 1 feature or closely related features. Order by dependencies.

### 4. Output

Create `.claude/harness/` and write:

**spec.md**: harness_id, tech stack, feature decomposition, sprint plan, eval settings (test_command, lint_command, etc.)

**Per-sprint contract.md**:
```markdown
---
sprint_id: "sprint-001"
title: "(feature title)"
status: planned
depends_on: []
---
## Objective
## Acceptance Criteria
- AC-001: (verifiable criterion)
## Implementation Scope
### Files to Create
### Files to Modify
### Files to Preserve
## Constraints
```

**harness_state.json**:
```json
{
  "harness_id": "(uuid)",
  "phase": "sprinting",
  "spec_path": ".claude/harness/spec.md",
  "sprints": [{"sprint_id": "sprint-001", "title": "...", "status": "planned", "attempt": 0, "max_attempts": 3}],
  "current_sprint_index": 0,
  "total_context_resets": 0,
  "project_root": "."
}
```
