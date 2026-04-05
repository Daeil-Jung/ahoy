from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import load_module

validate_harness = load_module("test_validate_harness_module", "scripts/validate_harness.py")


def write_harness_state(base: Path, status: str = "generated", sprint_id: str = "sprint-001", attempt: int = 0) -> None:
    harness_dir = base / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    sprint = {"sprint_id": sprint_id, "status": status}
    if attempt:
        sprint["attempt"] = attempt
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [sprint],
            }
        ),
        encoding="utf-8",
    )


def write_contract(base: Path, content: str, sprint_id: str = "sprint-001") -> Path:
    contract_path = base / ".claude" / "harness" / "sprints" / sprint_id / "contract.md"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(content, encoding="utf-8")
    return contract_path


def write_issues(base: Path, payload: dict, sprint_id: str = "sprint-001") -> Path:
    issues_path = base / ".claude" / "harness" / "sprints" / sprint_id / "issues.json"
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    issues_path.write_text(json.dumps(payload), encoding="utf-8")
    return issues_path


def issue_payload(
    verdict: str = "pass",
    status_action: str = "passed",
    models_valid: list[str] | None = None,
) -> dict:
    return {
        "evaluated_at": "2026-03-29T00:00:00+00:00",
        "models_used": ["codex", "claude"],
        "models_valid": models_valid or ["codex", "claude"],
        "verdict": verdict,
        "model_verdicts": {"codex": verdict, "claude": verdict},
        "status_action": status_action,
    }


# ── Utility / helper tests ─────────────────────────────────────


def test_load_json_and_state_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="rework")

    state = validate_harness.load_state()

    assert validate_harness.get_current_sprint(state) == "sprint-001"
    assert validate_harness.get_current_status(state) == "rework"


def test_verify_issues_integrity_detects_missing_fields_and_bad_timestamp(tmp_path: Path):
    missing = tmp_path / "missing.json"
    missing.write_text('{"verdict": "pass"}', encoding="utf-8")
    invalid_ts = tmp_path / "invalid.json"
    invalid_ts.write_text(
        json.dumps(
            {
                "evaluated_at": "bad",
                "models_used": [],
                "models_valid": [],
                "verdict": "pass",
                "model_verdicts": {},
                "status_action": "passed",
            }
        ),
        encoding="utf-8",
    )

    assert validate_harness.verify_issues_integrity(tmp_path / "absent.json") == "FAIL:file_not_found"
    assert validate_harness.verify_issues_integrity(missing).startswith("FAIL:missing_fields:")
    assert validate_harness.verify_issues_integrity(invalid_ts) == "FAIL:invalid_timestamp"


# ── 1. guard-eval-files ─────────────────────────────────────────


def test_check_guard_eval_files_always_blocks():
    with pytest.raises(SystemExit):
        validate_harness.check_guard_eval_files()


# ── 2. pre-gen ──────────────────────────────────────────────────


def test_check_pre_gen_requires_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)

    with pytest.raises(SystemExit):
        validate_harness.check_pre_gen()


def test_check_pre_gen_passes_with_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    write_contract(tmp_path, "## Implementation Scope")

    validate_harness.check_pre_gen()


# ── 3. pre-state-write ──────────────────────────────────────────


def test_check_pre_state_write_requires_valid_evaluation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")

    with pytest.raises(SystemExit):
        validate_harness.check_pre_state_write()


def test_check_pre_state_write_passes_with_two_valid_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_issues(tmp_path, issue_payload(models_valid=["codex", "claude"]))

    validate_harness.check_pre_state_write()

    assert (tmp_path / ".claude" / "harness" / "harness_state.json.bak").exists()


def test_check_pre_state_write_blocks_single_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_issues(tmp_path, issue_payload(models_valid=["codex"]))

    with pytest.raises(SystemExit):
        validate_harness.check_pre_state_write()


def test_check_pre_state_write_skips_non_generated_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="planned")

    # Should not raise even without issues.json
    validate_harness.check_pre_state_write()


def test_check_pre_state_write_blocks_invalid_issues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    # Write an incomplete issues.json (missing required fields)
    issues_path = tmp_path / ".claude" / "harness" / "sprints" / "sprint-001" / "issues.json"
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    issues_path.write_text('{"verdict": "pass"}', encoding="utf-8")

    with pytest.raises(SystemExit):
        validate_harness.check_pre_state_write()


# ── 4. post-eval ────────────────────────────────────────────────


def test_check_post_eval_blocks_error_verdict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    payload = issue_payload(verdict="error", status_action="error")
    payload["error_reason"] = "All models failed"
    write_issues(tmp_path, payload)

    with pytest.raises(SystemExit):
        validate_harness.check_post_eval()


def test_check_post_eval_blocks_unknown_verdict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_issues(tmp_path, issue_payload(verdict="unknown", status_action="unknown"))

    with pytest.raises(SystemExit):
        validate_harness.check_post_eval()


def test_check_post_eval_blocks_insufficient_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_issues(tmp_path, issue_payload(verdict="pass", status_action="passed", models_valid=["codex"]))

    with pytest.raises(SystemExit):
        validate_harness.check_post_eval()


def test_check_post_eval_passes_when_models_are_valid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_issues(tmp_path, issue_payload(verdict="partial_pass", status_action="passed"))

    validate_harness.check_post_eval()


def test_check_post_eval_blocks_missing_issues_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    # No issues.json written

    with pytest.raises(SystemExit):
        validate_harness.check_post_eval()


# ── 5. post-state-write ─────────────────────────────────────────


def test_check_post_state_write_rolls_back_invalid_passed_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="passed")
    state_file = tmp_path / ".claude" / "harness" / "harness_state.json"
    backup_file = Path(f"{state_file}.bak")
    backup_file.write_text('{"restored": true}', encoding="utf-8")
    write_issues(tmp_path, issue_payload(verdict="fail", status_action="failed"))

    with pytest.raises(SystemExit):
        validate_harness.check_post_state_write()

    assert json.loads(state_file.read_text(encoding="utf-8")) == {"restored": True}


def test_check_post_state_write_passes_for_consistent_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="passed")
    state_file = tmp_path / ".claude" / "harness" / "harness_state.json"
    backup_file = Path(f"{state_file}.bak")
    backup_file.write_text('{"old": true}', encoding="utf-8")
    write_issues(tmp_path, issue_payload(verdict="pass", status_action="passed"))

    validate_harness.check_post_state_write()

    assert not backup_file.exists()


def test_check_post_state_write_skips_non_passed_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")

    # Should not raise for non-passed status
    validate_harness.check_post_state_write()


def test_check_post_state_write_rolls_back_missing_issues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="passed")
    state_file = tmp_path / ".claude" / "harness" / "harness_state.json"
    backup_file = Path(f"{state_file}.bak")
    backup_file.write_text('{"restored": true}', encoding="utf-8")
    # No issues.json written

    with pytest.raises(SystemExit):
        validate_harness.check_post_state_write()

    assert json.loads(state_file.read_text(encoding="utf-8")) == {"restored": True}


def test_check_post_state_write_warns_no_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="passed")
    write_issues(tmp_path, issue_payload(verdict="fail", status_action="failed"))
    # No backup file

    with pytest.raises(SystemExit):
        validate_harness.check_post_state_write()

    captured = capsys.readouterr()
    assert "No backup file" in captured.out or "auto-rollback not possible" in captured.out


# ── 6. circuit-breaker ──────────────────────────────────────────


def test_check_circuit_breaker_blocks_on_repeated_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [{"sprint_id": "sprint-001", "status": "failed", "attempt": 2}],
            }
        ),
        encoding="utf-8",
    )
    sprint_dir = harness_dir / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)
    issues = [{"category": "functional", "description": "same bug"}]
    (sprint_dir / "issues.json").write_text(json.dumps({"issues": issues, "status_action": "failed"}), encoding="utf-8")
    (sprint_dir / "issues.json.attempt-1").write_text(json.dumps({"issues": issues}), encoding="utf-8")

    with pytest.raises(SystemExit):
        validate_harness.check_circuit_breaker()


def test_check_circuit_breaker_skips_when_passed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [{"sprint_id": "sprint-001", "status": "passed", "attempt": 2}],
            }
        ),
        encoding="utf-8",
    )
    sprint_dir = harness_dir / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)
    (sprint_dir / "issues.json").write_text(json.dumps({"issues": [], "status_action": "passed"}), encoding="utf-8")

    validate_harness.check_circuit_breaker()


def test_check_circuit_breaker_skips_first_attempt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [{"sprint_id": "sprint-001", "status": "failed", "attempt": 1}],
            }
        ),
        encoding="utf-8",
    )
    sprint_dir = harness_dir / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)
    issues = [{"category": "functional", "description": "bug"}]
    (sprint_dir / "issues.json").write_text(json.dumps({"issues": issues, "status_action": "failed"}), encoding="utf-8")

    # attempt < 2 should not trigger circuit breaker
    validate_harness.check_circuit_breaker()


def test_check_circuit_breaker_passes_on_different_issues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [{"sprint_id": "sprint-001", "status": "failed", "attempt": 2}],
            }
        ),
        encoding="utf-8",
    )
    sprint_dir = harness_dir / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)
    (sprint_dir / "issues.json").write_text(
        json.dumps({"issues": [{"category": "functional", "description": "new bug"}], "status_action": "failed"}),
        encoding="utf-8",
    )
    (sprint_dir / "issues.json.attempt-1").write_text(
        json.dumps({"issues": [{"category": "functional", "description": "old bug"}]}),
        encoding="utf-8",
    )

    validate_harness.check_circuit_breaker()


def test_circuit_breaker_archives_gen_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """check_circuit_breaker() should archive gen_report.md alongside issues.json."""
    monkeypatch.chdir(tmp_path)

    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps({
            "current_sprint_index": 0,
            "sprints": [{"sprint_id": "sprint-001", "status": "generated", "attempt": 2}],
        }),
        encoding="utf-8",
    )

    sprint_dir = harness_dir / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)

    (sprint_dir / "issues.json").write_text(
        json.dumps({
            "status_action": "failed",
            "issues": [{"category": "functional", "description": "Bug A"}],
        }),
        encoding="utf-8",
    )

    gen_content = "# Gen Report\n\nAttempt 2 approach details here."
    (sprint_dir / "gen_report.md").write_text(gen_content, encoding="utf-8")

    (sprint_dir / "issues.json.attempt-1").write_text(
        json.dumps({"issues": [{"category": "functional", "description": "Bug A"}]}),
        encoding="utf-8",
    )

    try:
        validate_harness.check_circuit_breaker()
    except SystemExit:
        pass

    archived = sprint_dir / "gen_report.md.attempt-2"
    assert archived.exists(), "gen_report.md should be archived as gen_report.md.attempt-2"
    assert archived.read_text(encoding="utf-8") == gen_content


def test_circuit_breaker_archives_issues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """check_circuit_breaker() should archive issues.json as issues.json.attempt-N."""
    monkeypatch.chdir(tmp_path)

    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps({
            "current_sprint_index": 0,
            "sprints": [{"sprint_id": "sprint-001", "status": "failed", "attempt": 1}],
        }),
        encoding="utf-8",
    )

    sprint_dir = harness_dir / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)

    issues_content = {"status_action": "failed", "issues": [{"category": "test", "description": "test failure"}]}
    (sprint_dir / "issues.json").write_text(json.dumps(issues_content), encoding="utf-8")

    validate_harness.check_circuit_breaker()

    archived = sprint_dir / "issues.json.attempt-1"
    assert archived.exists(), "issues.json should be archived as issues.json.attempt-1"


def test_issues_signature_helper():
    issues = [
        {"category": "functional", "description": "Scope regression bug"},
        {"category": "test", "description": "TODO left behind"},
    ]
    assert validate_harness._issues_signature(issues) == {
        "functional::scope regression bug",
        "test::todo left behind",
    }


# ── main() ──────────────────────────────────────────────────────


def test_main_exits_zero_outside_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(validate_harness.sys, "argv", ["validate_harness.py", "pre-gen"])

    with pytest.raises(SystemExit) as exc:
        validate_harness.main()

    assert exc.value.code == 0


def test_main_rejects_unknown_check_in_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    monkeypatch.setattr(validate_harness.sys, "argv", ["validate_harness.py", "unknown"])

    with pytest.raises(SystemExit) as exc:
        validate_harness.main()

    assert exc.value.code == 1


def test_main_dispatches_known_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    called: list[str] = []
    monkeypatch.setitem(validate_harness.CHECKS, "pre-gen", lambda: called.append("pre-gen"))
    monkeypatch.setattr(validate_harness.sys, "argv", ["validate_harness.py", "pre-gen"])

    validate_harness.main()

    assert called == ["pre-gen"]


def test_checks_dict_contains_all_six_checks():
    expected = {"guard-eval-files", "pre-gen", "pre-state-write", "post-eval", "post-state-write", "circuit-breaker"}
    assert set(validate_harness.CHECKS.keys()) == expected
