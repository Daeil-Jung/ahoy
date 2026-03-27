---
harness_id: "{{harness_id}}"
created: "{{created}}"
status: draft
---

# Project Spec

## Goal

{{project_goal}}

## Tech Stack

{{tech_stack}}

## Feature Decomposition

{{features}}

## Sprint Plan

{{sprint_plan}}

## Evaluation Strategy

```yaml
eval_strategy:
  test_runner: {{test_runner}}
  test_command: "{{test_command}}"
  coverage_threshold: {{coverage_threshold}}
  lint_command: "{{lint_command}}"
  type_check_command: "{{type_check_command}}"
  ui_testing:
    enabled: {{ui_testing_enabled}}
    framework: {{ui_framework}}
    base_url: "{{ui_base_url}}"
    start_command: "{{ui_start_command}}"
```

## Constraints

{{constraints}}

## Assumptions

{{assumptions}}
