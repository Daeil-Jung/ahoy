from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import load_module

eval_dispatch = load_module("e2e_eval_dispatch", "scripts/eval_dispatch.py")
validate_harness = load_module("e2e_validate_harness", "scripts/validate_harness.py")


CONTRACT = """\
## Acceptance Criteria
- AC-001: Login endpoint returns 200
- AC-002: Error handling returns 4xx

## Implementation Scope
### Files to Create
- `src/auth.py`
### Files to Modify
- `scripts/example.py`
### Files to Preserve
- `README.md`
"""

GEN_REPORT = """\
### Files Created
- `src/auth.py`
### Files Modified
- `scripts/example.py`
"""


def _make_model_response(
    verdict: str = "pass",
    issues: list | None = None,
    suggestion: str | None = None,
) -> str:
    issue_list = issues or []
    if suggestion:
        issue_list = [{"id": "ISS-1", "severity": "minor", "description": "nit", "suggestion": suggestion}]
    return json.dumps({
        "verdict": verdict,
        "objections": ["minor nit"],
        "criteria_results": [
            {"criterion_id": "AC-001", "description": "Login endpoint", "verdict": verdict, "evidence": "ok"},
            {"criterion_id": "AC-002", "description": "Error handling", "verdict": verdict, "evidence": "ok"},
        ],
        "issues": issue_list,
        "passed_criteria": ["AC-001", "AC-002"] if verdict == "pass" else [],
        "failed_criteria": [] if verdict == "pass" else ["AC-001", "AC-002"],
        "summary": f"model {verdict}",
        "reasoning_chain": {
            "code_understanding": "analyzed",
            "ac_verification": "verified",
            "quality_assessment": "assessed",
            "final_reasoning": "concluded",
        },
    })


@pytest.fixture
def sprint_env(tmp_path: Path):
    """Full sprint environment with contract, gen_report, source code, and harness state."""
    project_root = tmp_path / "project"
    harness_dir = project_root / ".claude" / "harness"
    sprint_dir = harness_dir / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)

    (sprint_dir / "contract.md").write_text(CONTRACT, encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text(GEN_REPORT, encoding="utf-8")

    # Source files
    (project_root / "src").mkdir(parents=True)
    (project_root / "src" / "auth.py").write_text("def login(): return 200\n", encoding="utf-8")
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")

    # harness_state.json
    (harness_dir / "harness_state.json").write_text(
        json.dumps({
            "current_sprint_index": 0,
            "sprints": [{"sprint_id": "sprint-001", "status": "generated", "attempt": 1, "max_attempts": 3}],
        }),
        encoding="utf-8",
    )

    return sprint_dir, project_root


def test_e2e_eval_produces_valid_issues_for_validator(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: _make_model_response("pass"),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    exit_code = eval_dispatch.main()
    assert exit_code == 0

    issues_path = sprint_dir / "issues.json"
    assert issues_path.exists()

    integrity = validate_harness.verify_issues_integrity(issues_path)
    assert integrity == "OK"


def test_e2e_pass_verdict_allows_state_transition(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: _make_model_response("pass"),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )
    eval_dispatch.main()

    # Validate pre_state_write passes
    monkeypatch.chdir(project_root)
    validate_harness.check_pre_state_write()

    # Update state to passed
    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["status"] = "passed"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    # Create backup for post_state_write
    Path(f"{state_file}.bak").write_text(json.dumps({"old": True}), encoding="utf-8")

    validate_harness.check_post_state_write()  # Should not raise


def test_e2e_fail_verdict_blocks_wrong_transition(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: _make_model_response("fail", issues=[{"id": "ISS-1", "severity": "major", "description": "broken"}]),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )
    eval_dispatch.main()

    monkeypatch.chdir(project_root)

    # Wrongly set status to passed
    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    old_state = state_file.read_text(encoding="utf-8")
    state = json.loads(old_state)
    state["sprints"][0]["status"] = "passed"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    Path(f"{state_file}.bak").write_text(old_state, encoding="utf-8")

    with pytest.raises(SystemExit):
        validate_harness.check_post_state_write()

    # Verify rollback happened
    restored = json.loads(state_file.read_text(encoding="utf-8"))
    assert restored["sprints"][0]["status"] == "generated"


def test_e2e_circuit_breaker_across_rework(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()

    issues = [
        {"category": "functional", "description": "null pointer in login"},
        {"category": "test", "description": "test_auth fails"},
    ]

    # Attempt 1 archived
    (sprint_dir / "issues.json.attempt-1").write_text(
        json.dumps({"issues": issues}), encoding="utf-8",
    )
    # Attempt 2 current — same issues
    (sprint_dir / "issues.json").write_text(
        json.dumps({"issues": issues, "status_action": "failed"}), encoding="utf-8",
    )

    result = validate_harness.detect_failure_pattern(sprint_dir, 2)

    assert result["circuit_break"] is True
    assert "null pointer in login" in result["repeated_issues"]
    assert "test_auth fails" in result["repeated_issues"]
    assert result["recommendation"] == "failed"


def test_e2e_convergence_tracking_accumulates(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: _make_model_response("pass"),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    # Run first evaluation
    eval_dispatch.main()

    state_path = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert "convergence_history" in state["sprints"][0]
    assert len(state["sprints"][0]["convergence_history"]) == 1
    assert state["sprints"][0]["convergence_history"][0]["convergence_ratio"] == 1.0

    # Check cost tracking was updated
    assert "cost_tracking" in state
    assert state["cost_tracking"]["total_eval_calls"] == 2  # codex + claude


def test_e2e_config_driven_model_selection(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    sprint_dir, project_root = sprint_env
    called_models: list[str] = []

    def fake_call(model: str, prompt: str, timeout: int = 600) -> str:
        called_models.append(model)
        return _make_model_response("pass")

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call)
    monkeypatch.setattr(
        eval_dispatch, "load_config",
        lambda: {"eval_models": ["gemini", "claude"], "min_models": 2, "cost_limit": None},
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    assert sorted(called_models) == ["claude", "gemini"]


def test_e2e_suggestion_field_survives_pipeline(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: _make_model_response(
            "partial_pass",
            suggestion=f"fix line 42 ({model})",
        ),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))

    suggestions = [issue.get("suggestion", "") for issue in payload["issues"]]
    assert any("fix line 42" in s for s in suggestions)
    assert len(suggestions) == 2  # One from each model
