---
name: ahoy
description: "AHOY Orchestrator — Automatically orchestrates the full lifecycle (Planner → Generator → Evaluator loop) of the AI coding harness. Start a new harness or resume an interrupted one."
argument-hint: "[project request]"
model: opus
effort: max
---

# AHOY — Agent Harness for Orchestrated Yielding

Run the full lifecycle of the AI coding harness with a single input.
Automatically orchestrates the Planner → Generator → Evaluator (external model) loop.

## Usage

- `/ahoy <project request>` — Start a new harness
- `/ahoy` — Resume an interrupted harness

$ARGUMENTS

## Overall Flow

```
Start/Resume
  ↓
Check state (.claude/harness/harness_state.json)
  ↓
None → Initialize → Call /ahoy:ahoy-plan
  ↓
SPRINTING → Depending on current sprint status:
  planned    → Request contract confirmation (AskUserQuestion)
  contracted → Call /ahoy:ahoy-gen (Agent tool)
  generated  → Call /ahoy:ahoy-eval (Agent tool, external model evaluation)
  passed     → Move to next sprint
  failed     → rework (attempt < max_attempts) or user decision
  skipped    → Move to next sprint
  rework     → Re-call /ahoy:ahoy-gen (rework mode)
  ↓
All passed/skipped → Completion report
```

## User Guidance Output Rules

**Provide rich explanations of the current situation to the user at every phase transition.**
Instead of short status codes, convey in natural language what you are about to do / why / what comes next.

### Output Format at Phase Start

When entering each major phase, present guidance to the user in the following format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## [Phase] Phase Title
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Current state**: (what has been completed and where we are)
**Current task**: (the work to be performed in this phase)
**Next phase**: (the flow that follows)
```

### Sprint Progress Dashboard

Output the overall progress as a table each time the sprint loop is entered:

```
## Sprint Progress

| # | Sprint | Status | Attempts | External Evaluation |
|---|--------|--------|----------|---------------------|
| 1 | sprint-001: Auth API | passed | 1/3 | codex: pass, claude: pass |
| 2 | sprint-002: User CRUD | **in progress** | 0/3 | - |
| 3 | sprint-003: Permission Management | waiting | - | - |

**Progress**: 1/3 sprints completed (33%)
```

### Detailed Guidance by Phase

**When starting a new harness**:
```
## Harness Initialization

Analyzing the project request to create an implementation plan.

**Request summary**: (1-2 line summary of user request)
**Detected tech stack**: (pyproject.toml → Python/FastAPI etc.)
**Approach**: The Planner decomposes the request into feature units and converts each feature into a sprint contract.
  Each sprint proceeds through a loop where the Generator (Claude) implements → the Evaluator (external model) independently verifies.

Running the Planner...
```

**When resuming an existing harness**:
```
## Harness Resume

Restoring existing harness state.

**Harness ID**: (harness_id)
**Created**: (created)
**Current position**: sprint-NNN (title) — status state
**Completed sprints**: N/M
**Handoff history**: N context resets

(Description of next action based on current state)
```

**When requesting contract confirmation**:
```
## Sprint Contract Review: sprint-NNN

Please review the implementation scope and acceptance criteria for the next sprint.

(Full contract.md content)

**Key points of this contract**:
- N files to create, M files to modify
- K acceptance criteria (all verified by external models)
- Expected dependencies: (depends_on sprint list or "none")
```
→ AskUserQuestion: "Proceed with this contract?", "Modifications needed", "Skip this sprint"

- "Proceed" → Change status to `contracted`
- "Modifications needed" → Incorporate user feedback, rewrite contract.md, confirm again
- "Skip" → Change status to `skipped`, move to next sprint

**When starting Generator**:
```
## Generator Execution: sprint-NNN

Implementing code and tests according to the contract.

**Implementation goal**: (contract title)
**Acceptance criteria**: AC-001 ~ AC-NNN (N total)
**Scope**: Create N files / Modify M files
**Mode**: (new implementation | rework — attempt N/3)

Spawning Generator sub-agent...
```

**After Generator completion**:
```
## Generator Complete: sprint-NNN

Implementation is complete. Proceeding with external model evaluation.

**Implementation results**:
- Files created: (list)
- Files modified: (list)
- Additions/deletions: +N / -M lines
- Test execution: N passed, M failed

Next, external models (Codex, Claude separate process) will independently evaluate this implementation.
Claude (Generator) does not evaluate its own code — this is the core principle of the harness.
```

**When starting Evaluator**:
```
## External Model Evaluation: sprint-NNN

External models verify the code in a context completely separated from the Generator.

**Evaluation models**: (codex, claude etc.)
**Evaluation criteria**: Acceptance criteria from contract.md (AC-001 ~ AC-NNN)
**Evaluation method**: Each model reviews independently → consensus calculated (any fail → final fail)

Running eval_dispatch.py...
```

**Evaluation result report**:
```
## Evaluation Results: sprint-NNN

**Final verdict: PASS** (or FAIL / PARTIAL_PASS)

| Model | Verdict | Issue Count |
|-------|---------|-------------|
| codex | pass | 0 |
| claude | pass | 1 (minor) |

**Passed criteria**: AC-001, AC-002, AC-003
**Failed criteria**: (none or list)

(If PASS)
→ Moving to the next sprint.

(If FAIL)
### Issues Found (N total)

| ID | Severity | Found By | Description |
|----|----------|----------|-------------|
| ISS-001 | blocker | codex | (description) |
| ISS-002 | major | claude | (description) |

→ Starting rework (attempt N/3). The Generator will fix the above issues.
```

**When starting rework**:
```
## Rework: sprint-NNN (attempt N/3)

Fixing issues found by external models.

**Issues to fix**: N total (blocker: X, major: Y, minor: Z)
**Key issues**:
1. ISS-001 (blocker, codex): (description) → Fix direction: (suggested_fix)
2. ISS-002 (major, claude): (description) → Fix direction: (suggested_fix)

Re-running Generator in rework mode...
```

**After 3 failures**:
```
## Rework Limit Reached: sprint-NNN

Failed to pass external model evaluation after 3 attempts.

**Attempt history**:
- 1st: fail (2 blockers)
- 2nd: partial_pass (1 major)
- 3rd: fail (1 major)

**Recurring issues**: (commonly flagged patterns)
```
→ AskUserQuestion: "Continue trying (increase attempt count)", "Skip this sprint", "Abort harness"

- "Continue trying" → Increase `max_attempts`, continue rework
- "Skip" → Change status to `skipped`, move to next sprint
- "Abort harness" → Change phase to `aborted`, output summary of results so far

## 1. Start New Harness

If a project request is provided:

1. Create `.claude/harness/` directory (including sprints/, handoffs/)
2. Spawn Planner sub-agent via Agent tool with `/ahoy:ahoy-plan` content included in the prompt
3. Planner generates spec.md + sprint contracts + harness_state.json
4. Present the first sprint's contract to the user for confirmation

## 2. Resume Existing Harness

When called without arguments:

1. Read `.claude/harness/harness_state.json`
2. If a recent handoff exists in `handoffs/`, read it as well
3. Execute the next step from the current state

## 3. Sprint Loop

### Contract Confirmation (planned → contracted)

Display the contract.md content and key summary to the user and request confirmation.

### Generator Invocation (contracted → generated)

Spawn a Generator sub-agent via Agent tool:
- Include the full content of the `/ahoy:ahoy-gen` skill in the prompt
- Pass the sprint path and project root as context
- After completion, status → `generated`
- **Output implementation result summary to the user upon completion**

### Evaluator Invocation (generated → passed/failed)

Spawn an Evaluator sub-agent via Agent tool:
- Include the full content of the `/ahoy:ahoy-eval` skill in the prompt
- **Context separation required**: Pass only the following information; never include the Generator's conversation history:
  - Sprint path: `.claude/harness/sprints/sprint-NNN/`
  - Project root path
  - spec.md path (for evaluation settings reference)
- **Prohibited**: Passing Generator's opinions/context such as "what judgments it made" or "why it implemented this way"
- **Prohibited**: Including the Generator sub-agent's result message in the Evaluator prompt
- Evaluator runs eval_dispatch.py for external model evaluation
- Based on verdict, status → `passed` or `failed`
- **Output evaluation result table to the user upon completion**

### Rework (failed → rework → generated)

1. Organize the issue list by severity and display to the user
2. Increment the `attempt` field of the current sprint in `harness_state.json` by 1
3. If `attempt < max_attempts` (default 3):
   - status → `rework`
   - Re-call Generator in rework mode
4. If `attempt >= max_attempts`, summarize the attempt history and recurring patterns, then AskUserQuestion
   - If "Continue trying" is selected, increase `max_attempts`

### Sprint Complete → Next Sprint

1. Increment current_sprint_index
2. **Output progress dashboard**
3. Move to next sprint contract confirmation
4. If it was the last sprint, process completion

## 4. Context Reset Decision

Every 3 completed sprints or when .claude/harness/ files exceed 50:

1. Generate handoff document: `.claude/harness/handoffs/handoff-NNN.md`
   - Spec summary + completed sprint results + current state + remaining contracts
2. Save harness_state.json
3. Inform the user:
   ```
   ## Context Reset Recommended

   N sprints have been completed and the conversation context has grown long.
   For optimal performance, it is recommended to continue in a new session.

   **Saved state**: .claude/harness/handoffs/handoff-NNN.md
   **How to resume**: Run `/ahoy` in a new Claude Code session
   **Remaining sprints**: M
   ```

## 5. Completion

When all sprints are passed:

1. phase → `complete`
2. Output completion summary:
   ```
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ## Harness Complete
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   **Harness ID**: (id)
   **Total sprints**: N completed
   **Total attempts**: M (including rework)
   **Context resets**: K

   ### Results by Sprint

   | # | Sprint | Attempts | Final Verdict | Evaluation Models |
   |---|--------|----------|---------------|-------------------|
   | 1 | sprint-001: Auth API | 1 | pass | codex: pass, claude: pass |
   | 2 | sprint-002: User CRUD | 2 | pass | codex: pass, claude: partial→pass |
   | 3 | sprint-003: Permission Management | 1 | pass | codex: pass, claude: pass |

   ### Files Created/Modified
   (full file list)

   All sprints have passed external model evaluation.
   ```

## Enforced Rules (verified by hooks)

- Cannot pass a sprint without external model evaluation (eval_dispatch.py)
- Cannot run the Generator without contract.md
- Generator and Evaluator must be spawned as separate Agents (context separation)
