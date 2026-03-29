from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from conftest import load_module

validate_harness = load_module("test_validate_harness_module", "scripts/validate_harness.py")


def write_harness_state(base: Path, status: str = "generated", sprint_id: str = "sprint-001") -> None:
    harness_dir = base / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [{"sprint_id": sprint_id, "status": status}],
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


def test_command_extractors_ignore_placeholders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / ".claude" / "harness" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        '\n'.join(
            [
                'test_command: "uv run pytest"',
                'lint_command: "{{ lint_command }}"',
                'type_check_command: "uv run mypy scripts"',
                "coverage_threshold: 85",
            ]
        ),
        encoding="utf-8",
    )

    assert validate_harness.get_test_command() == "uv run pytest"
    assert validate_harness.get_lint_command() == ""
    assert validate_harness.get_type_check_command() == "uv run mypy scripts"
    assert validate_harness.get_coverage_threshold() == 85


def test_load_json_and_state_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="rework")

    state = validate_harness.load_state()

    assert validate_harness.get_current_sprint(state) == "sprint-001"
    assert validate_harness.get_current_status(state) == "rework"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("Coverage: 85%", 85.0),
        ("85% coverage", 85.0),
        ("TOTAL 10 0 100%", 100.0),
        ("Total coverage: 85.3%", 85.3),
        ("no coverage data", None),
    ],
)
def test_parse_coverage_percent(output: str, expected: float | None):
    assert validate_harness._parse_coverage_percent(output) == expected


def test_parse_scope_from_contract_reads_all_sections(tmp_path: Path):
    contract_path = tmp_path / "contract.md"
    contract_path.write_text(
        "\n".join(
            [
                "## Implementation Scope",
                "### Files to Create",
                "- `tests/test_eval_dispatch.py`",
                "### Files to Modify",
                "- `scripts/eval_dispatch.py`",
                "### Files to Preserve",
                "- `README.md`",
                "## Acceptance Criteria",
                "- AC-001",
            ]
        ),
        encoding="utf-8",
    )

    create, modify, preserve = validate_harness.parse_scope_from_contract(contract_path)

    assert create == ["tests/test_eval_dispatch.py"]
    assert modify == ["scripts/eval_dispatch.py"]
    assert preserve == ["README.md"]


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


def test_failure_pattern_helpers(tmp_path: Path):
    issues = [
        {"category": "functional", "description": "Scope regression bug"},
        {"category": "test", "description": "TODO left behind"},
    ]
    assert validate_harness.classify_failure_type(issues) == ["scope_violation", "test_failure"]
    assert validate_harness._issues_signature(issues) == {
        "functional::scope regression bug",
        "test::todo left behind",
    }

    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "issues.json.attempt-1").write_text(json.dumps({"issues": issues}), encoding="utf-8")
    (sprint_dir / "issues.json").write_text(json.dumps({"issues": issues}), encoding="utf-8")

    assert validate_harness._load_attempt_issues(sprint_dir, 1) == issues
    detected = validate_harness.detect_failure_pattern(sprint_dir, 2)
    assert detected["circuit_break"]
    assert "scope regression bug" in detected["repeated_issues"]


def test_check_scope_allows_in_scope_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    write_contract(
        tmp_path,
        "\n".join(
            [
                "## Implementation Scope",
                "### Files to Modify",
                "- `scripts/eval_dispatch.py`",
            ]
        ),
    )
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": str(tmp_path / "scripts" / "eval_dispatch.py")}),
    )

    validate_harness.check_scope()


def test_check_scope_blocks_preserved_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    write_contract(
        tmp_path,
        "\n".join(
            [
                "## Implementation Scope",
                "### Files to Preserve",
                "- `README.md`",
            ]
        ),
    )
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": str(tmp_path / "README.md")}),
    )

    with pytest.raises(SystemExit):
        validate_harness.check_scope()


def test_check_scope_allows_plugin_root_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    write_contract(tmp_path, "## Implementation Scope\n### Files to Modify\n- `scripts/other.py`")
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": str(plugin_root / "scripts" / "validate_harness.py")}),
    )

    validate_harness.check_scope()


def test_check_scope_blocks_out_of_scope_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    write_contract(tmp_path, "## Implementation Scope\n### Files to Modify\n- `scripts/eval_dispatch.py`")
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": str(tmp_path / "docs" / "README.ko.md")}),
    )

    with pytest.raises(SystemExit):
        validate_harness.check_scope()


def test_path_matching_helper():
    assert validate_harness._path_matches_scope_entry("src/app.py", "app.py")
    assert validate_harness._path_matches_scope_entry("src/app.py", "src/app.py")
    assert not validate_harness._path_matches_scope_entry("src/app.py", "other.py")


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


def test_check_post_eval_blocks_error_verdict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    payload = issue_payload(verdict="error", status_action="error")
    payload["error_reason"] = "All models failed"
    write_issues(tmp_path, payload)

    with pytest.raises(SystemExit):
        validate_harness.check_post_eval()


def test_check_post_eval_passes_when_models_are_valid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_issues(tmp_path, issue_payload(verdict="partial_pass", status_action="passed"))

    validate_harness.check_post_eval()


def test_check_guard_eval_files_always_blocks():
    with pytest.raises(SystemExit):
        validate_harness.check_guard_eval_files()


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


def test_audit_final_scope_blocks_out_of_scope_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_contract(tmp_path, "## Implementation Scope\n### Files to Modify\n- `scripts/eval_dispatch.py`")

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = iter(
        [
            Result(0, "ok"),
            Result(0, "docs/README.ko.md\n"),
            Result(0, ""),
        ]
    )
    monkeypatch.setattr(validate_harness.subprocess, "run", lambda *args, **kwargs: next(calls))

    with pytest.raises(SystemExit):
        validate_harness.audit_final_scope()


def test_post_edit_quality_detects_markers_and_respects_allowlist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ahoy-allowlist").write_text("TODO: allowed\n", encoding="utf-8")
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "scripts/example.py", "content": "TODO: blocked\nTODO: allowed\n"}),
    )

    with pytest.raises(SystemExit):
        validate_harness.check_post_edit_quality()


def test_post_edit_quality_skips_test_files(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "tests/test_example.py", "content": "TODO: allowed in tests"}),
    )

    validate_harness.check_post_edit_quality()


def test_run_tests_with_coverage_blocks_when_threshold_not_met(monkeypatch: pytest.MonkeyPatch):
    class Result:
        returncode = 0
        stdout = "Coverage: 79%"
        stderr = ""

    monkeypatch.setattr(validate_harness.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(SystemExit):
        validate_harness._run_tests_with_coverage("uv run pytest", 80)


def test_run_verification_command_blocks_on_non_zero_exit(monkeypatch: pytest.MonkeyPatch):
    class Result:
        returncode = 1

    monkeypatch.setattr(validate_harness.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(SystemExit):
        validate_harness._run_verification_command("lint", "uv run ruff check .")


def test_check_pre_commit_runs_all_configured_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude" / "harness").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude" / "harness" / "spec.md").write_text(
        '\n'.join(
            [
                'test_command: "uv run pytest"',
                'lint_command: "uv run ruff check ."',
                'type_check_command: "uv run mypy scripts"',
                "coverage_threshold: 80",
            ]
        ),
        encoding="utf-8",
    )
    called: list[tuple[str, object]] = []
    monkeypatch.setattr(
        validate_harness,
        "_run_tests_with_coverage",
        lambda command, threshold: called.append((command, threshold)),
    )
    monkeypatch.setattr(
        validate_harness,
        "_run_verification_command",
        lambda label, command: called.append((label, command)),
    )

    validate_harness.check_pre_commit()

    assert called == [
        ("uv run pytest", 80),
        ("lint", "uv run ruff check ."),
        ("type check", "uv run mypy scripts"),
    ]


def test_check_pre_push_blocks_inconsistent_passed_sprint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "spec.md").write_text("", encoding="utf-8")
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [{"sprint_id": "sprint-001", "status": "passed"}],
            }
        ),
        encoding="utf-8",
    )
    write_issues(tmp_path, issue_payload(verdict="fail", status_action="failed"))

    with pytest.raises(SystemExit):
        validate_harness.check_pre_push()


def test_check_pre_push_passes_consistent_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "spec.md").write_text("", encoding="utf-8")
    (harness_dir / "harness_state.json").write_text(
        json.dumps(
            {
                "current_sprint_index": 0,
                "sprints": [{"sprint_id": "sprint-001", "status": "passed"}],
            }
        ),
        encoding="utf-8",
    )
    write_issues(tmp_path, issue_payload(verdict="pass", status_action="passed"))

    validate_harness.check_pre_push()


def test_hooks_json_references_expected_validation_checks():
    hooks = json.loads(
        (Path(__file__).resolve().parents[1] / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )
    commands = [
        hook["command"]
        for stage in hooks["hooks"].values()
        for matcher in stage
        for hook in matcher["hooks"]
        if hook["type"] == "command"
    ]

    assert any("validate_harness.py\" scope-check" in command for command in commands)
    assert any("validate_harness.py\" pre-state-write" in command for command in commands)
    assert any("validate_harness.py\" post-eval" in command for command in commands)


def test_main_exits_zero_outside_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(validate_harness.sys, "argv", ["validate_harness.py", "scope-check"])

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
    monkeypatch.setitem(validate_harness.CHECKS, "scope-check", lambda: called.append("scope"))
    monkeypatch.setattr(validate_harness.sys, "argv", ["validate_harness.py", "scope-check"])

    validate_harness.main()

    assert called == ["scope"]


# ── v0.2.0 gap-fill tests ───────────────────────────────────────


def test_audit_final_scope_allows_harness_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_contract(tmp_path, "## Implementation Scope\n### Files to Modify\n- `scripts/eval_dispatch.py`")

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = iter([
        Result(0, "ok"),                                     # git rev-parse HEAD
        Result(0, ".claude/harness/harness_state.json\n"),   # git diff HEAD
        Result(0, ""),                                       # git diff --cached
    ])
    monkeypatch.setattr(validate_harness.subprocess, "run", lambda *args, **kwargs: next(calls))

    validate_harness.audit_final_scope()  # Should not raise


def test_audit_final_scope_blocks_preserved_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_contract(
        tmp_path,
        "## Implementation Scope\n### Files to Modify\n- `scripts/eval_dispatch.py`\n### Files to Preserve\n- `README.md`",
    )

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = iter([
        Result(0, "ok"),                     # git rev-parse HEAD
        Result(0, "README.md\n"),            # git diff HEAD
        Result(0, ""),                       # git diff --cached
    ])
    monkeypatch.setattr(validate_harness.subprocess, "run", lambda *args, **kwargs: next(calls))

    with pytest.raises(SystemExit):
        validate_harness.audit_final_scope()


def test_audit_final_scope_skips_unborn_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_contract(tmp_path, "## Implementation Scope\n### Files to Modify\n- `scripts/eval_dispatch.py`")

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        validate_harness.subprocess, "run",
        lambda *args, **kwargs: Result(128, stderr="fatal: Needed a single revision"),
    )

    validate_harness.audit_final_scope()  # Should not raise


def test_detect_failure_pattern_skips_first_attempt(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()

    result = validate_harness.detect_failure_pattern(sprint_dir, 1)

    assert result["circuit_break"] is False


def test_detect_failure_pattern_no_previous_file(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "issues.json").write_text(
        json.dumps({"issues": [{"category": "functional", "description": "bug"}]}),
        encoding="utf-8",
    )

    result = validate_harness.detect_failure_pattern(sprint_dir, 2)

    assert result["circuit_break"] is False


def test_detect_failure_pattern_no_issues_key(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "issues.json").write_text('{"verdict": "pass"}', encoding="utf-8")
    (sprint_dir / "issues.json.attempt-1").write_text(
        json.dumps({"issues": [{"category": "functional", "description": "bug"}]}),
        encoding="utf-8",
    )

    result = validate_harness.detect_failure_pattern(sprint_dir, 2)

    assert result["circuit_break"] is False


def test_post_edit_quality_detects_stub_pass(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "scripts/example.py", "content": "def foo():\n    pass\n"}),
    )

    with pytest.raises(SystemExit):
        validate_harness.check_post_edit_quality()


def test_post_edit_quality_detects_ellipsis(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "scripts/example.py", "content": "def foo():\n    ...\n"}),
    )

    with pytest.raises(SystemExit):
        validate_harness.check_post_edit_quality()


def test_post_edit_quality_detects_not_implemented(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "scripts/example.py", "content": "def foo():\n    raise NotImplementedError\n"}),
    )

    with pytest.raises(SystemExit):
        validate_harness.check_post_edit_quality()


def test_post_edit_quality_uses_new_string_from_edit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "scripts/example.py", "new_string": "TODO: implement this\n"}),
    )

    with pytest.raises(SystemExit):
        validate_harness.check_post_edit_quality()


def test_post_edit_quality_skips_binary_extension(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "image.png", "content": "TODO: this should not be detected"}),
    )

    validate_harness.check_post_edit_quality()  # Should not raise


def test_check_pre_push_runs_all_and_checks_consistent_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "spec.md").write_text(
        '\n'.join([
            'test_command: "uv run pytest"',
            'lint_command: "uv run ruff check ."',
            'type_check_command: "uv run mypy scripts"',
            "coverage_threshold: 80",
        ]),
        encoding="utf-8",
    )
    (harness_dir / "harness_state.json").write_text(
        json.dumps({
            "current_sprint_index": 0,
            "sprints": [{"sprint_id": "sprint-001", "status": "passed"}],
        }),
        encoding="utf-8",
    )
    write_issues(tmp_path, issue_payload(verdict="pass", status_action="passed"))

    called: list[tuple] = []
    monkeypatch.setattr(
        validate_harness, "_run_tests_with_coverage",
        lambda command, threshold: called.append(("test", command, threshold)),
    )
    monkeypatch.setattr(
        validate_harness, "_run_verification_command",
        lambda label, command: called.append((label, command)),
    )

    validate_harness.check_pre_push()

    assert ("test", "uv run pytest", 80) in called
    assert ("lint", "uv run ruff check .") in called
    assert ("type check", "uv run mypy scripts") in called


def test_audit_final_scope_filters_plugin_root_relative(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path, status="generated")
    write_contract(tmp_path, "## Implementation Scope\n### Files to Modify\n- `scripts/eval_dispatch.py`")
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_dir))

    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = iter([
        Result(0, "ok"),                          # git rev-parse HEAD
        Result(0, "my-plugin/scripts/hook.py\n"), # git diff HEAD (plugin-root file)
        Result(0, ""),                            # git diff --cached
    ])
    monkeypatch.setattr(validate_harness.subprocess, "run", lambda *args, **kwargs: next(calls))

    validate_harness.audit_final_scope()  # Should not raise — plugin-root files are allowed


def test_hooks_json_covers_all_expected_check_types():
    hooks = json.loads(
        (Path(__file__).resolve().parents[1] / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )
    commands = []
    for stage in hooks["hooks"].values():
        for matcher in stage:
            for hook in matcher["hooks"]:
                if hook["type"] == "command":
                    commands.append(hook["command"])

    combined = " ".join(commands)
    expected_checks = [
        "scope-check", "pre-state-write", "post-state-write",
        "pre-gen", "post-eval", "guard-eval-files",
        "audit-final-scope", "pre-commit", "pre-push",
        "post-edit-quality", "circuit-breaker", "anti-rationalization",
        "record-read", "stale-read-check",
    ]
    for check in expected_checks:
        assert check in combined, f"Missing hook check: {check}"


# ── gen_report.md archiving tests ──────────────────────────────


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


# ── Anti-rationalization gate tests ──────────────────────────────


def _setup_anti_rationalization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    contract_acs: list[str],
    gen_report_content: str = "",
    *,
    tool_input: dict | None = None,
    gen_report_on_disk: str | None = None,
) -> None:
    """Helper to set up harness state, contract, and CLAUDE_TOOL_INPUT for anti-rationalization tests."""
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    ac_lines = "\n".join(f"- {ac}" for ac in contract_acs)
    write_contract(
        tmp_path,
        f"## Implementation Scope\n### Files to Modify\n- `src/app.py`\n\n## Acceptance Criteria\n{ac_lines}",
    )
    if tool_input is None:
        tool_input = {"file_path": "gen_report.md", "content": gen_report_content}
    monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps(tool_input))
    if gen_report_on_disk is not None:
        report_path = tmp_path / ".claude" / "harness" / "sprints" / "sprint-001" / "gen_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(gen_report_on_disk, encoding="utf-8")


def test_anti_rationalization_passes_all_acs_covered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works", "AC-002 Tests pass"],
        "## AC Coverage\n| AC | Status |\n| AC-001 | pass |\n| AC-002 | pass |\n",
    )
    validate_harness.check_anti_rationalization()


def test_anti_rationalization_blocks_rationalized_ac(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works", "AC-002 Tests pass"],
        "## AC Coverage\n| AC-001 | pass |\n| AC-002 | pass |\n\n## Unresolved Issues\n- AC-001: not needed for current implementation\n",
    )
    with pytest.raises(SystemExit):
        validate_harness.check_anti_rationalization()


def test_anti_rationalization_blocks_missing_ac(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works", "AC-002 Tests pass"],
        "## AC Coverage\n| AC-001 | pass |\n",
    )
    with pytest.raises(SystemExit):
        validate_harness.check_anti_rationalization()


def test_anti_rationalization_allows_honest_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works", "AC-002 Tests pass"],
        "## AC Coverage\n| AC-001 | pass |\n| AC-002 | fail |\n\n## Unresolved Issues\n- AC-002: test suite fails due to timeout in CI\n",
    )
    validate_harness.check_anti_rationalization()


def test_anti_rationalization_detects_korean_patterns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works"],
        "## AC Coverage\n| AC-001 | pass |\n\n## Unresolved Issues\n- AC-001: 현재 구조상 불필요\n",
    )
    with pytest.raises(SystemExit):
        validate_harness.check_anti_rationalization()


def test_anti_rationalization_skips_non_harness_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    # No harness state set up — should pass silently
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "gen_report.md", "content": "## Unresolved Issues\n- AC-001: not needed\n"}),
    )
    validate_harness.check_anti_rationalization()


def test_anti_rationalization_edit_tool_reconstructs_post_edit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Edit tool: old_string->new_string replacement on disk content reconstructs full post-edit state."""
    disk_content = "## AC Coverage\n| AC-001 | pass |\n| AC-002 | TODO |\n"
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works", "AC-002 Tests pass"],
        tool_input={"file_path": "gen_report.md", "old_string": "| AC-002 | TODO |", "new_string": "| AC-002 | pass |"},
        gen_report_on_disk=disk_content,
    )
    validate_harness.check_anti_rationalization()


def test_anti_rationalization_edit_tool_detects_rationalization(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Edit tool: rationalization pattern added via edit is caught in reconstructed post-edit state."""
    disk_content = "## AC Coverage\n| AC-001 | pass |\n\n## Unresolved Issues\n- AC-001: placeholder\n"
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works"],
        tool_input={"file_path": "gen_report.md", "old_string": "- AC-001: placeholder", "new_string": "- AC-001: not needed for current implementation"},
        gen_report_on_disk=disk_content,
    )
    with pytest.raises(SystemExit):
        validate_harness.check_anti_rationalization()


def test_anti_rationalization_edit_tool_missing_ac(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Edit tool: AC missing from reconstructed post-edit state is caught."""
    disk_content = "## AC Coverage\n| AC-001 | pass |\n| AC-002 | pass |\n"
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works", "AC-002 Tests pass"],
        tool_input={"file_path": "gen_report.md", "old_string": "| AC-002 | pass |", "new_string": "| removed |"},
        gen_report_on_disk=disk_content,
    )
    with pytest.raises(SystemExit):
        validate_harness.check_anti_rationalization()


def test_anti_rationalization_write_tool_ignores_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Write tool: content field is the full file, disk content is irrelevant."""
    _setup_anti_rationalization(
        monkeypatch,
        tmp_path,
        ["AC-001 Feature X works", "AC-002 Tests pass"],
        gen_report_content="## AC Coverage\n| AC-001 | pass |\n| AC-002 | pass |\n",
        gen_report_on_disk="## Old content with no AC references\n",
    )
    validate_harness.check_anti_rationalization()


# ── Stale-read detection tests ────────────────────────────────


def test_record_read_hash_stores_hash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "example.py"
    target.write_text("print('hello')", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps({"file_path": str(target)}))
    monkeypatch.setattr(validate_harness, "_READ_HASH_FILE", harness_dir / ".read_hashes.json")

    validate_harness.record_read_hash()

    hashes = json.loads((harness_dir / ".read_hashes.json").read_text(encoding="utf-8"))
    assert str(target) in hashes
    expected_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    assert hashes[str(target)] == expected_hash


def test_stale_read_passes_when_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "example.py"
    target.write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr(validate_harness, "_READ_HASH_FILE", harness_dir / ".read_hashes.json")
    monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps({"file_path": str(target)}))

    validate_harness.record_read_hash()
    validate_harness.check_stale_read()


def test_stale_read_blocks_when_changed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "example.py"
    target.write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr(validate_harness, "_READ_HASH_FILE", harness_dir / ".read_hashes.json")
    monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps({"file_path": str(target)}))

    validate_harness.record_read_hash()
    target.write_text("print('changed')", encoding="utf-8")

    with pytest.raises(SystemExit):
        validate_harness.check_stale_read()


def test_stale_read_allows_new_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(validate_harness, "_READ_HASH_FILE", harness_dir / ".read_hashes.json")
    new_file = tmp_path / "new_file.py"
    monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps({"file_path": str(new_file)}))

    validate_harness.check_stale_read()


def test_stale_read_warns_no_read_record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "example.py"
    target.write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr(validate_harness, "_READ_HASH_FILE", harness_dir / ".read_hashes.json")
    monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps({"file_path": str(target)}))

    validate_harness.check_stale_read()

    captured = capsys.readouterr()
    assert "No Read recorded" in captured.err


def test_stale_read_multiple_reads_uses_latest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    harness_dir = tmp_path / ".claude" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "example.py"
    target.write_text("version1", encoding="utf-8")
    monkeypatch.setattr(validate_harness, "_READ_HASH_FILE", harness_dir / ".read_hashes.json")
    monkeypatch.setenv("CLAUDE_TOOL_INPUT", json.dumps({"file_path": str(target)}))

    validate_harness.record_read_hash()
    target.write_text("version2", encoding="utf-8")
    validate_harness.record_read_hash()

    validate_harness.check_stale_read()


def test_anti_rationalization_ac_parser_checklist_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """AC parser should match checklist formats like '- [ ] AC-001' and '- [x] AC-001'."""
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    contract_content = (
        "## Acceptance Criteria\n"
        "- [ ] AC-001 Feature X works\n"
        "- [x] AC-002 Tests pass\n"
    )
    write_contract(tmp_path, f"## Implementation Scope\n### Files to Modify\n- `src/app.py`\n\n{contract_content}")
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "gen_report.md", "content": "## AC Coverage\n| AC-001 | pass |\n| AC-002 | pass |\n"}),
    )
    validate_harness.check_anti_rationalization()


def test_anti_rationalization_ac_parser_bold_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """AC parser should match bold format like '- **AC-001**'."""
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    contract_content = (
        "## Acceptance Criteria\n"
        "- **AC-001** Feature X works\n"
        "- **AC-002** Tests pass\n"
    )
    write_contract(tmp_path, f"## Implementation Scope\n### Files to Modify\n- `src/app.py`\n\n{contract_content}")
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({"file_path": "gen_report.md", "content": "## AC Coverage\n| AC-001 | pass |\n"}),
    )
    # AC-002 missing from report → should block
    with pytest.raises(SystemExit):
        validate_harness.check_anti_rationalization()


def test_anti_rationalization_edit_tool_reconstruction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Edit tool should reconstruct post-edit content by applying old_string→new_string on disk."""
    monkeypatch.chdir(tmp_path)
    write_harness_state(tmp_path)
    write_contract(
        tmp_path,
        "## Implementation Scope\n### Files to Modify\n- `src/app.py`\n\n## Acceptance Criteria\n- AC-001 Feature X\n- AC-002 Tests pass\n",
    )
    # Write existing gen_report.md to disk with AC-001 covered
    gen_report_path = tmp_path / ".claude" / "harness" / "sprints" / "sprint-001" / "gen_report.md"
    gen_report_path.write_text("## AC Coverage\n| AC-001 | pass |\n| AC-002 | TODO |\n", encoding="utf-8")
    # Simulate Edit tool replacing "TODO" with "pass"
    monkeypatch.setenv(
        "CLAUDE_TOOL_INPUT",
        json.dumps({
            "file_path": str(gen_report_path),
            "old_string": "| AC-002 | TODO |",
            "new_string": "| AC-002 | pass |",
        }),
    )
    validate_harness.check_anti_rationalization()
