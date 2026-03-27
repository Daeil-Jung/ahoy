---
name: ahoy-plan
description: "AHOY Planner — Converts user prompts into a project spec (spec.md) and sprint contracts (contract.md). Called by the orchestrator (/ahoy)."
disable-model-invocation: true
argument-hint: "[project request]"
model: opus
effort: max
---

# Harness Planner

Converts user prompts into a project spec and sprint contracts.

## Input

$ARGUMENTS

## User Guidance Output Rules

As each step progresses, explain to the user in natural language what is being done and why.

## Procedure

### 1. Tech Stack Detection

Scan the following files from the project root to identify the tech stack:
- `package.json` → Node.js/React/Vue etc.
- `pyproject.toml` / `requirements.txt` → Python/FastAPI/Django etc.
- `go.mod` → Go
- `Cargo.toml` → Rust
- `CLAUDE.md` → Project-specific context

After detection, output to the user:
```
## Tech Stack Detection

Analyzed the project root to identify the tech stack.

**Detected files**: pyproject.toml, CLAUDE.md
**Tech stack**: Python 3.12 / FastAPI / uv
**Test framework**: pytest
**Lint**: ruff

(Project context summary gathered from existing CLAUDE.md)
```

If the project is empty, use AskUserQuestion to ask about the tech stack.

### 2. process_harness Artifact Integration (if present)

If a `docs/` directory exists:
- `docs/02_architecture/` → Reflect architecture decisions
- `docs/06_wbs/` → Utilize for sprint mapping
- `docs/04_api_spec/` → Include API endpoints

If integrated, output to the user:
```
## process_harness Artifact Integration

Found existing design artifacts and incorporating them into the sprint plan.

**Integrated artifacts**:
- Architecture decisions: (N key decisions)
- WBS: (referenced existing work breakdown structure)
- API spec: (N endpoints)
```

### 3. Feature Decomposition

Decompose user requests into independently implementable features:
- Assign a FEAT-ID to each feature
- Specify dependencies between features
- Write **verifiable** acceptance criteria (AC) for each feature
  - O "POST /api/users → returns 201 and creates user in DB"
  - X "Implement user management"

Ambiguous requirements → Resolve via AskUserQuestion.

After decomposition, output to the user:
```
## Feature Decomposition Results

Decomposed the user request into N independent features.

| FEAT-ID | Feature Name | AC Count | Dependencies |
|---------|-------------|----------|--------------|
| FEAT-001 | Auth API | 3 | - |
| FEAT-002 | User CRUD | 4 | FEAT-001 |
| FEAT-003 | Permission Management | 3 | FEAT-001, FEAT-002 |

**Total acceptance criteria**: 10 (all verified by external models)
```

### 4. Sprint Organization

1 sprint = 1 feature or a group of closely related features. Ordered by dependencies.

After organization, output to the user:
```
## Sprint Plan

Organized N features into M sprints.

| Sprint | Included Features | Estimated File Count | Acceptance Criteria |
|--------|-------------------|----------------------|---------------------|
| sprint-001 | FEAT-001 | Create 3 / Modify 1 | AC-001 ~ AC-003 |
| sprint-002 | FEAT-002 | Create 4 / Modify 2 | AC-004 ~ AC-007 |
| sprint-003 | FEAT-003 | Create 2 / Modify 3 | AC-008 ~ AC-010 |

**Execution order**: sprint-001 → sprint-002 → sprint-003 (based on dependencies)
**Evaluation method**: External model (Codex + Claude separate process) consensus evaluation per sprint
```

### 5. Output Generation

Create the `.claude/harness/` directory and write the following files:

**`.claude/harness/spec.md`**:
```markdown
---
harness_id: "(uuid hex 12 digits)"
created: "(ISO 8601)"
---
# Project Spec
## Objective
## Tech Stack
## Feature Decomposition (by FEAT-ID)
## Sprint Organization
## Evaluation Settings
eval_strategy:
  test_runner: (pytest|vitest|jest|go test|cargo test)
  test_command: "(execution command)"
  lint_command: "(lint command)"
  ui_testing:
    enabled: (true|false)
```

**Per-sprint `.claude/harness/sprints/sprint-NNN/contract.md`**:
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
## Evaluation Method
## Constraints
```

**`.claude/harness/harness_state.json`**:
```json
{
  "harness_id": "(same as spec)",
  "phase": "sprinting",
  "spec_path": ".claude/harness/spec.md",
  "sprints": [{"sprint_id": "sprint-001", "title": "...", "status": "planned", "attempt": 0, "max_attempts": 3}],
  "current_sprint_index": 0,
  "total_context_resets": 0,
  "project_root": "."
}
```

After file creation, output to the user:
```
## Planner Complete

Harness initialization is complete.

**Generated files**:
- `.claude/harness/spec.md` — Project spec
- `.claude/harness/harness_state.json` — Master state
- `.claude/harness/sprints/sprint-001/contract.md` — Sprint 1 contract
- `.claude/harness/sprints/sprint-002/contract.md` — Sprint 2 contract
- ...

**Next step**: Reviewing the first sprint (sprint-001) contract.
```
