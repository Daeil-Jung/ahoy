from __future__ import annotations

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
