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


# ── Full eval pipeline (eval -> validation -> state transitions) ──


def test_e2e_eval_produces_valid_issues_for_validator(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """eval_dispatch produces issues.json that passes validate_harness integrity check."""
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


def test_e2e_full_pass_happy_path(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """Full pipeline: eval pass -> pre_state_write -> state=passed -> post_state_write."""
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
    monkeypatch.chdir(project_root)

    # 1. pre_state_write passes
    validate_harness.check_pre_state_write()

    # 2. Update state to passed
    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["status"] = "passed"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    Path(f"{state_file}.bak").write_text(json.dumps({"old": True}), encoding="utf-8")

    # 3. post_state_write passes
    validate_harness.check_post_state_write()


# ── Pass/fail verdict state transitions ──────────────────────────


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

    monkeypatch.chdir(project_root)
    validate_harness.check_pre_state_write()

    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["status"] = "passed"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    Path(f"{state_file}.bak").write_text(json.dumps({"old": True}), encoding="utf-8")

    validate_harness.check_post_state_write()  # Should not raise


def test_e2e_fail_verdict_blocks_wrong_transition(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """Fail verdict -> wrongly set passed -> post_state_write rollback."""
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


def test_e2e_fail_verdict_transitions_to_rework(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """Fail verdict -> state set to rework -> pre_state_write allows it (non-generated state)."""
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: _make_model_response(
            "fail", issues=[{"id": "ISS-1", "severity": "major", "description": "broken"}],
        ),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "fail"
    assert payload["status_action"] == "failed"

    monkeypatch.chdir(project_root)
    state_file = project_root / ".claude" / "harness" / "harness_state.json"

    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["status"] = "rework"
    state["sprints"][0]["attempt"] = 2
    state_file.write_text(json.dumps(state), encoding="utf-8")

    # pre_state_write only blocks generated -> pass without eval, so rework is fine
    validate_harness.check_pre_state_write()


def test_e2e_partial_pass_with_blocker_blocks_transition(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """partial_pass + blocker issue -> status_action='failed' -> forced passed -> rollback."""
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: json.dumps({
            "verdict": "partial_pass",
            "objections": ["blocker found"],
            "criteria_results": [
                {"criterion_id": "AC-001", "verdict": "pass", "evidence": "ok"},
                {"criterion_id": "AC-002", "verdict": "fail", "evidence": "broken"},
            ],
            "issues": [{"id": "ISS-1", "severity": "blocker", "description": "critical bug"}],
            "passed_criteria": ["AC-001"],
            "failed_criteria": ["AC-002"],
            "summary": "partial",
            "reasoning_chain": {"code_understanding": "a", "ac_verification": "b", "quality_assessment": "c", "final_reasoning": "d"},
        }),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["status_action"] == "failed"

    monkeypatch.chdir(project_root)
    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    old_state = state_file.read_text(encoding="utf-8")
    state = json.loads(old_state)
    state["sprints"][0]["status"] = "passed"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    Path(f"{state_file}.bak").write_text(old_state, encoding="utf-8")

    with pytest.raises(SystemExit):
        validate_harness.check_post_state_write()

    restored = json.loads(state_file.read_text(encoding="utf-8"))
    assert restored["sprints"][0]["status"] == "generated"


def test_e2e_partial_pass_without_blocker_allows_pass(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """partial_pass with only minor issues -> status_action='passed' -> transition allowed."""
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: json.dumps({
            "verdict": "partial_pass",
            "objections": ["minor nit"],
            "criteria_results": [
                {"criterion_id": "AC-001", "verdict": "pass", "evidence": "ok"},
                {"criterion_id": "AC-002", "verdict": "pass", "evidence": "ok"},
            ],
            "issues": [{"id": "ISS-1", "severity": "minor", "description": "style nit"}],
            "passed_criteria": ["AC-001", "AC-002"],
            "failed_criteria": [],
            "summary": "partial",
            "reasoning_chain": {"code_understanding": "a", "ac_verification": "b", "quality_assessment": "c", "final_reasoning": "d"},
        }),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["status_action"] == "passed"

    monkeypatch.chdir(project_root)

    validate_harness.check_pre_state_write()

    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["status"] = "passed"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    Path(f"{state_file}.bak").write_text(json.dumps({"old": True}), encoding="utf-8")

    validate_harness.check_post_state_write()  # No rollback


def test_e2e_error_verdict_blocks_all_transitions(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """Error verdict -> post_eval blocks."""
    sprint_dir, project_root = sprint_env

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: "COMPLETELY INVALID",
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "error"

    monkeypatch.chdir(project_root)
    with pytest.raises(SystemExit):
        validate_harness.check_post_eval()


def test_e2e_single_model_blocked_by_quorum(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """One model errors -> only 1 valid -> pre_state_write blocks."""
    sprint_dir, project_root = sprint_env

    def fake_call(model: str, prompt: str, timeout: int = 600) -> str:
        if model == "codex":
            return "INVALID NOT JSON"
        return _make_model_response("pass")

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call)
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert len(payload["models_valid"]) < 2

    monkeypatch.chdir(project_root)
    with pytest.raises(SystemExit):
        validate_harness.check_pre_state_write()


def test_e2e_full_fail_to_rework_to_pass_flow(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """Complete rework cycle: fail -> rework -> re-eval pass -> transition to passed."""
    sprint_dir, project_root = sprint_env

    attempt = {"n": 0}

    def fake_call(model: str, prompt: str, timeout: int = 600) -> str:
        if attempt["n"] == 0:
            return _make_model_response("fail", issues=[{"id": "ISS-1", "severity": "major", "description": "broken"}])
        return _make_model_response("pass")

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call)
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    # Attempt 1: fail
    eval_dispatch.main()
    payload1 = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload1["status_action"] == "failed"

    # Simulate orchestrator updating state to rework
    monkeypatch.chdir(project_root)
    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["status"] = "generated"  # back to generated for re-eval
    state["sprints"][0]["attempt"] = 2
    state_file.write_text(json.dumps(state), encoding="utf-8")

    # Attempt 2: pass
    attempt["n"] = 1
    eval_dispatch.main()
    payload2 = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload2["status_action"] == "passed"

    # Should allow state transition
    validate_harness.check_pre_state_write()

    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["status"] = "passed"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    Path(f"{state_file}.bak").write_text(json.dumps({"old": True}), encoding="utf-8")

    validate_harness.check_post_state_write()


# ── Circuit breaker across rework attempts ───────────────────────


def test_e2e_circuit_breaker_across_rework(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """After eval -> circuit breaker archives and detects repeated failures."""
    sprint_dir, project_root = sprint_env
    monkeypatch.chdir(project_root)

    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["attempt"] = 2
    state_file.write_text(json.dumps(state), encoding="utf-8")

    issues = [
        {"category": "functional", "description": "null pointer in login"},
        {"category": "test", "description": "test_auth fails"},
    ]

    # Archive attempt 1
    (sprint_dir / "issues.json.attempt-1").write_text(
        json.dumps({"issues": issues}), encoding="utf-8",
    )
    # Current attempt has same issues
    (sprint_dir / "issues.json").write_text(
        json.dumps({"issues": issues, "status_action": "failed"}), encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        validate_harness.check_circuit_breaker()


def test_e2e_circuit_breaker_no_trigger_on_different_issues(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """Different issues across attempts -> no circuit break."""
    sprint_dir, project_root = sprint_env
    monkeypatch.chdir(project_root)

    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["attempt"] = 2
    state_file.write_text(json.dumps(state), encoding="utf-8")

    (sprint_dir / "issues.json.attempt-1").write_text(
        json.dumps({"issues": [{"category": "functional", "description": "null pointer"}]}),
        encoding="utf-8",
    )
    (sprint_dir / "issues.json").write_text(
        json.dumps({"issues": [{"category": "test", "description": "timeout error"}], "status_action": "failed"}),
        encoding="utf-8",
    )

    # Should not raise -- different issues
    validate_harness.check_circuit_breaker()


def test_e2e_circuit_breaker_archives_attempts(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """After eval -> circuit breaker archives issues.json.attempt-N and gen_report.md.attempt-N."""
    sprint_dir, project_root = sprint_env
    monkeypatch.chdir(project_root)

    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["sprints"][0]["attempt"] = 1
    state_file.write_text(json.dumps(state), encoding="utf-8")

    monkeypatch.setattr(
        eval_dispatch, "call_model",
        lambda model, prompt, timeout=600: _make_model_response(
            "fail", issues=[{"id": "ISS-1", "severity": "major", "description": "bug X"}],
        ),
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )
    eval_dispatch.main()

    # Run circuit breaker (attempt=1, so archives but doesn't compare)
    validate_harness.check_circuit_breaker()

    assert (sprint_dir / "issues.json.attempt-1").exists()
    assert (sprint_dir / "gen_report.md.attempt-1").exists()


# ── Config-driven model selection ────────────────────────────────


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
        lambda: {"eval_models": ["gemini", "claude"], "min_models": 2},
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    assert sorted(called_models) == ["claude", "gemini"]


def test_e2e_config_driven_perspectives(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """Config assigns perspectives -> each model gets different prompt."""
    sprint_dir, project_root = sprint_env
    captured: dict[str, str] = {}

    def fake_call(model: str, prompt: str, timeout: int = 600) -> str:
        captured[model] = prompt
        return _make_model_response("pass")

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call)
    monkeypatch.setattr(
        eval_dispatch, "load_config",
        lambda: {
            "eval_models": ["codex", "gemini"],
            "min_models": 2,
            "eval_perspectives": {"codex": "accuracy_coverage", "gemini": "security_edge"},
        },
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,gemini", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    assert "Accuracy & Test Coverage" in captured["codex"]
    assert "Security & Edge Cases" in captured["gemini"]


# ── Sensitive data masking in eval prompts ───────────────────────


def test_e2e_sensitive_data_masked_in_eval_prompt(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """API key in source code -> masked before reaching external models."""
    sprint_dir, project_root = sprint_env

    (project_root / "src" / "auth.py").write_text(
        'API_KEY = "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234"\n'
        'PASSWORD = "super_secret_password_123"\n'
        "def login(): return 200\n",
        encoding="utf-8",
    )

    captured_prompts: list[str] = []

    def fake_call(model: str, prompt: str, timeout: int = 600) -> str:
        captured_prompts.append(prompt)
        return _make_model_response("pass")

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call)
    monkeypatch.setattr(
        eval_dispatch, "load_config",
        lambda: {
            "eval_models": ["codex", "claude"],
            "min_models": 2,
            "sensitive_data_masking": {"enabled": True, "extra_patterns": []},
        },
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()

    for prompt in captured_prompts:
        assert "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234" not in prompt
        assert "super_secret_password_123" not in prompt
        assert "MASKED" in prompt


# ── Guard evaluation files ───────────────────────────────────────


def test_e2e_guard_eval_files_after_real_eval(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """eval_dispatch writes issues.json legitimately -> guard blocks Claude direct write."""
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
    assert (sprint_dir / "issues.json").exists()

    monkeypatch.chdir(project_root)
    with pytest.raises(SystemExit):
        validate_harness.check_guard_eval_files()


# ── Pre-gen contract requirement ─────────────────────────────────


def test_e2e_pre_gen_blocks_without_contract(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """No contract.md -> pre-gen check blocks."""
    sprint_dir, project_root = sprint_env
    monkeypatch.chdir(project_root)

    (sprint_dir / "contract.md").unlink()

    with pytest.raises(SystemExit):
        validate_harness.check_pre_gen()


def test_e2e_pre_gen_passes_with_contract(
    monkeypatch: pytest.MonkeyPatch, sprint_env: tuple[Path, Path],
):
    """contract.md present -> pre-gen check passes."""
    _sprint_dir, project_root = sprint_env
    monkeypatch.chdir(project_root)

    validate_harness.check_pre_gen()  # Should not raise


# ── Suggestion field survives pipeline ───────────────────────────


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
