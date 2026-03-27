---
sprint_id: "{{sprint_id}}"
evaluated_at: "{{evaluated_at}}"
verdict: "{{verdict}}"
status_action: "{{status_action}}"
---

# Evaluation Report: {{sprint_id}}

## Summary

- **Verdict**: {{verdict}}
- **Status Action**: {{status_action}}
- **Passed Criteria**: {{passed_count}}/{{total_count}}
- **Issue Count**: {{issue_count}}

## Acceptance Criteria Verification

### Passed

{{passed_criteria}}

### Failed

{{failed_criteria}}

## Test Execution Results

```
{{test_output}}
```

## Code Quality

{{code_quality_notes}}

## Issues Found

{{issues_detail}}

## Recommendations

{{recommendations}}
