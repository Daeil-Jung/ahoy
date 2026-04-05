from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_module

eval_dispatch = load_module("test_eval_dispatch_module", "scripts/eval_dispatch.py")


# ── strip_generator_opinions ─────────────────────────────────────


def test_strip_generator_opinions_replaces_subjective_lines_and_keeps_facts():
    report = "\n".join(
        [
            "# Summary",
            "Implementation completed successfully.",
            "- `scripts/eval_dispatch.py`",
            "12 passed",
            "| AC | Status |",
            "|---|---|",
            "This works well in practice.",
        ]
    )

    sanitized = eval_dispatch.strip_generator_opinions(report)

    assert "[Generator opinion removed — verify the code directly]" in sanitized
    assert "- `scripts/eval_dispatch.py`" in sanitized
    assert "12 passed" in sanitized
    assert "|---|---|" in sanitized


def test_strip_generator_opinions_keeps_numeric_test_results_with_units():
    report = "\n".join(
        [
            "12 tests passed",
            "3 cases completed successfully",
            "+10 / -5 lines changed",
        ]
    )

    sanitized = eval_dispatch.strip_generator_opinions(report)

    assert "12 tests passed" in sanitized
    assert "3 cases completed" in sanitized
    assert "+10 / -5" in sanitized


# ── build_eval_prompt ─────────────────────────────────────────────


def test_build_eval_prompt_includes_sanitized_generator_report():
    prompt = eval_dispatch.build_eval_prompt(
        "AC-001",
        "Implementation completed successfully.",
        "### file.py\n```py\npass\n```",
    )

    assert "Sprint Contract" in prompt
    assert "Generator Report" in prompt
    assert "[Generator opinion removed — verify the code directly]" in prompt
    assert "Implementation completed successfully." not in prompt
    assert "### file.py" in prompt


def test_build_eval_prompt_no_perspective():
    prompt_default = eval_dispatch.build_eval_prompt("AC-001", "report", "code")
    prompt_none = eval_dispatch.build_eval_prompt("AC-001", "report", "code", perspective=None)
    assert prompt_default == prompt_none
    assert "Evaluation Perspective" not in prompt_default


def test_build_eval_prompt_with_accuracy_perspective():
    prompt = eval_dispatch.build_eval_prompt(
        "AC-001", "report", "code", perspective="accuracy_coverage"
    )
    assert "Accuracy & Test Coverage" in prompt
    assert "Test Coverage" in prompt
    assert "AC Satisfaction" in prompt


def test_build_eval_prompt_with_security_perspective():
    prompt = eval_dispatch.build_eval_prompt(
        "AC-001", "report", "code", perspective="security_edge"
    )
    assert "Security & Edge Cases" in prompt
    assert "Input validation" in prompt
    assert "Robustness" in prompt


def test_build_eval_prompt_unknown_perspective_ignored():
    prompt = eval_dispatch.build_eval_prompt(
        "AC-001", "report", "code", perspective="nonexistent_perspective"
    )
    assert "Evaluation Perspective" not in prompt


def test_build_eval_prompt_includes_priority_guide():
    prompt = eval_dispatch.build_eval_prompt(
        "AC-001",
        "Implementation completed successfully.",
        "### file.py\n```py\npass\n```",
    )
    assert "P0" in prompt
    assert "Priority Guide" in prompt


# ── parse_acceptance_criteria ─────────────────────────────────────


def test_parse_acceptance_criteria_extracts_explicit_and_implicit_ids():
    contract = "\n".join(
        [
            "## Acceptance Criteria",
            "- AC-001: first criterion",
            "- second criterion",
            "  - nested detail should be ignored",
        ]
    )

    assert eval_dispatch.parse_acceptance_criteria(contract) == [
        {"id": "AC-001", "description": "first criterion"},
        {"id": "AC-1", "description": "second criterion"},
    ]


# ── extract_json ──────────────────────────────────────────────────


def test_extract_json_reads_fenced_and_embedded_payloads():
    fenced = "```json\n{\"verdict\": \"pass\"}\n```"
    embedded = 'prefix {"verdict": "fail", "issues": []} suffix'

    assert eval_dispatch.extract_json(fenced) == {"verdict": "pass"}
    assert eval_dispatch.extract_json(embedded) == {"verdict": "fail", "issues": []}


def test_extract_json_returns_none_for_invalid_payload():
    assert eval_dispatch.extract_json("no json here") is None


# ── resolve_reported_files ────────────────────────────────────────


def test_resolve_reported_files_prefers_structured_inventory_and_dedupes():
    report = "\n".join(
        [
            "### Files Created",
            "- `scripts/new.py`",
            "### Files Modified",
            "- `scripts/old.py`",
            "- `scripts/new.py`",
        ]
    )

    assert eval_dispatch.resolve_reported_files(report) == [
        "scripts/new.py",
        "scripts/old.py",
    ]


def test_resolve_reported_files_supports_legacy_fallback():
    report = "- `scripts/one.py`\n- `scripts/two.py`\n"

    assert eval_dispatch.resolve_reported_files(report) == [
        "scripts/one.py",
        "scripts/two.py",
    ]


# ── collect_code_snippets ─────────────────────────────────────────


def test_collect_code_snippets_reads_declared_files(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "gen_report.md").write_text(
        "### Files Modified\n- `scripts/example.py`\n",
        encoding="utf-8",
    )
    project_root = tmp_path / "project"
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('hello')\n", encoding="utf-8")

    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root)

    assert "### scripts/example.py" in snippets
    assert "print('hello')" in snippets


def test_collect_code_snippets_requires_declared_and_existing_files(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "gen_report.md").write_text("No files here", encoding="utf-8")

    with pytest.raises(ValueError, match="No code files were declared"):
        eval_dispatch.collect_code_snippets(sprint_dir, tmp_path)


def test_collect_code_snippets_requires_gen_report(tmp_path: Path):
    with pytest.raises(ValueError, match="gen_report.md not found"):
        eval_dispatch.collect_code_snippets(tmp_path, tmp_path)


def test_collect_code_snippets_blocks_path_traversal(tmp_path: Path):
    """Paths with ../ that escape project root must be skipped by containment check."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    outside_file = tmp_path / "secret.py"
    outside_file.write_text("SECRET = 'leaked'", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text(
        "### Files Modified\n- `../secret.py`\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="No readable code files"):
        eval_dispatch.collect_code_snippets(sprint_dir, project_root)


def test_collect_code_snippets_allows_in_root_files(tmp_path: Path):
    """Files within project root should be collected normally."""
    project_root = tmp_path / "project"
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    file_path = project_root / "src" / "app.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('safe')\n", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text(
        "### Files Created\n- `src/app.py`\n",
        encoding="utf-8",
    )

    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root)
    assert "print('safe')" in snippets


# ── validate_objections ───────────────────────────────────────────


def test_validate_objections_normalizes_non_empty_strings():
    parsed = {"verdict": "pass", "objections": [" one ", "", 3]}

    validated = eval_dispatch.validate_objections(parsed, "codex")

    assert validated["objections"] == [" one "]


def test_validate_objections_skips_error_verdicts():
    parsed = {"verdict": "error", "error": "CLI failed"}

    validated = eval_dispatch.validate_objections(parsed, "codex")

    assert validated == parsed


# ── normalize_issue_priority ──────────────────────────────────────


def test_normalize_issue_priority_from_severity():
    issue = {"severity": "blocker"}
    result = eval_dispatch.normalize_issue_priority(issue)
    assert result["priority"] == "P0"
    assert result["severity"] == "blocker"


def test_normalize_issue_priority_from_priority():
    issue = {"priority": "P1"}
    result = eval_dispatch.normalize_issue_priority(issue)
    assert result["severity"] == "critical"
    assert result["priority"] == "P1"


def test_normalize_issue_priority_both_present():
    issue = {"severity": "minor", "priority": "P0"}
    result = eval_dispatch.normalize_issue_priority(issue)
    assert result["severity"] == "minor"
    assert result["priority"] == "P0"


def test_normalize_issue_priority_neither_present():
    issue = {"description": "some issue"}
    result = eval_dispatch.normalize_issue_priority(issue)
    assert result["priority"] == "P2"
    assert result["severity"] == "major"


# ── has_blocker_or_major / derive_status_action ───────────────────


def test_has_blocker_or_major_with_p0():
    assert eval_dispatch.has_blocker_or_major([{"priority": "P0"}])


def test_has_blocker_or_major_with_p3_only():
    assert not eval_dispatch.has_blocker_or_major([{"priority": "P3"}])


@pytest.mark.parametrize(
    ("verdict", "issues", "expected"),
    [
        ("pass", [], "passed"),
        ("partial_pass", [{"severity": "minor"}], "passed"),
        ("partial_pass", [{"severity": "major"}], "failed"),
        ("fail", [], "failed"),
        ("error", [], "error"),
    ],
)
def test_derive_status_action(verdict: str, issues: list[dict], expected: str):
    assert eval_dispatch.derive_status_action(verdict, issues) == expected


# ── _merge_criteria_results ───────────────────────────────────────


def test_merge_criteria_results_marks_missing_criteria_as_fail():
    merged, ratio = eval_dispatch._merge_criteria_results(
        {
            "codex": {
                "criteria_results": [
                    {
                        "criterion_id": "AC-1",
                        "description": "first",
                        "verdict": "pass",
                        "evidence": "ok",
                    }
                ]
            },
            "claude": {
                "criteria_results": [
                    {
                        "criterion_id": "AC-2",
                        "description": "second",
                        "verdict": "pass",
                        "evidence": "ok",
                    }
                ]
            },
        },
        known_criteria=[{"id": "AC-1", "description": "first"}, {"id": "AC-2", "description": "second"}],
    )

    assert ratio == 0.0
    assert [item["criterion_id"] for item in merged] == ["AC-1", "AC-2"]
    assert all(item["verdict"] == "fail" for item in merged)


def test_merge_criteria_results_normalizes_criterion_id_case():
    merged, ratio = eval_dispatch._merge_criteria_results(
        {
            "codex": {
                "criteria_results": [
                    {"criterion_id": "ac-001", "description": "first", "verdict": "pass", "evidence": "ok"},
                ]
            },
            "claude": {
                "criteria_results": [
                    {"criterion_id": "AC-001", "description": "first", "verdict": "pass", "evidence": "ok"},
                ]
            },
        },
        known_criteria=[{"id": "AC-001", "description": "first"}],
    )

    assert ratio == 1.0
    assert len(merged) == 1
    assert merged[0]["verdict"] == "pass"


def test_merge_criteria_results_handles_non_string_verdict():
    merged, ratio = eval_dispatch._merge_criteria_results(
        {
            "codex": {
                "criteria_results": [
                    {"criterion_id": "AC-001", "description": "first", "verdict": None, "evidence": "ok"},
                ]
            },
            "claude": {
                "criteria_results": [
                    {"criterion_id": "AC-001", "description": "first", "verdict": "pass", "evidence": "ok"},
                ]
            },
        },
        known_criteria=[{"id": "AC-001", "description": "first"}],
    )

    assert len(merged) == 1
    assert merged[0]["verdict"] == "fail"


def test_merge_criteria_results_full_pass_ratio():
    merged, ratio = eval_dispatch._merge_criteria_results(
        {
            "codex": {
                "criteria_results": [
                    {"criterion_id": "AC-1", "description": "first", "verdict": "pass", "evidence": "ok"},
                    {"criterion_id": "AC-2", "description": "second", "verdict": "pass", "evidence": "ok"},
                ]
            },
            "claude": {
                "criteria_results": [
                    {"criterion_id": "AC-1", "description": "first", "verdict": "pass", "evidence": "ok"},
                    {"criterion_id": "AC-2", "description": "second", "verdict": "pass", "evidence": "ok"},
                ]
            },
        },
        known_criteria=[{"id": "AC-1", "description": "first"}, {"id": "AC-2", "description": "second"}],
    )

    assert ratio == 1.0
    assert all(item["verdict"] == "pass" for item in merged)


def test_merge_criteria_results_empty_criteria():
    merged, ratio = eval_dispatch._merge_criteria_results(
        {"codex": {}, "claude": {}},
        known_criteria=[],
    )

    assert merged == []
    assert ratio == 0.0


# ── compute_consensus ─────────────────────────────────────────────


def test_compute_consensus_enforces_minimum_valid_models_and_merges_results():
    verdicts = {
        "codex": {
            "verdict": "partial_pass",
            "issues": [{"id": "ISS-1", "severity": "minor"}],
            "passed_criteria": ["AC-001"],
            "failed_criteria": [],
        },
        "claude": {
            "verdict": "fail",
            "issues": [{"id": "ISS-2", "severity": "major"}],
            "passed_criteria": [],
            "failed_criteria": ["AC-002"],
        },
        "gemini": {"verdict": "error"},
    }

    consensus = eval_dispatch.compute_consensus(verdicts, min_valid_models=2)

    assert consensus["consensus_verdict"] == "fail"
    assert consensus["model_verdicts"] == {
        "codex": {"verdict": "partial_pass"},
        "claude": {"verdict": "fail"},
        "gemini": {"verdict": "error"},
    }
    assert consensus["passed_criteria"] == ["AC-001"]
    assert consensus["failed_criteria"] == ["AC-002"]
    assert {issue["found_by"] for issue in consensus["issues"]} == {"codex", "claude"}


def test_compute_consensus_returns_error_when_not_enough_valid_models():
    verdicts = {
        "codex": {"verdict": "pass"},
        "claude": {"verdict": "error"},
    }

    consensus = eval_dispatch.compute_consensus(verdicts, min_valid_models=2)

    assert consensus["consensus_verdict"] == "error"
    assert "minimum 2 required" in consensus["reason"]


def test_compute_consensus_returns_error_when_all_models_fail():
    consensus = eval_dispatch.compute_consensus(
        {
            "codex": {"verdict": "error"},
            "claude": {"verdict": "error"},
        }
    )

    assert consensus["consensus_verdict"] == "error"
    assert consensus["reason"] == "All external model calls failed"


def test_compute_consensus_preserves_suggestion_field():
    verdicts = {
        "codex": {
            "verdict": "partial_pass",
            "issues": [{"id": "ISS-1", "severity": "minor", "suggestion": "fix line 42"}],
            "passed_criteria": ["AC-001"],
            "failed_criteria": [],
        },
        "claude": {
            "verdict": "partial_pass",
            "issues": [{"id": "ISS-2", "severity": "minor", "suggestion": "refactor method"}],
            "passed_criteria": ["AC-001"],
            "failed_criteria": [],
        },
    }

    consensus = eval_dispatch.compute_consensus(verdicts, min_valid_models=2)

    suggestions = [issue["suggestion"] for issue in consensus["issues"] if "suggestion" in issue]
    assert "fix line 42" in suggestions
    assert "refactor method" in suggestions


def test_compute_consensus_merges_objections_from_all_models():
    verdicts = {
        "codex": {
            "verdict": "pass",
            "issues": [],
            "objections": ["improve logging"],
            "passed_criteria": [],
            "failed_criteria": [],
        },
        "claude": {
            "verdict": "pass",
            "issues": [],
            "objections": ["add error handling"],
            "passed_criteria": [],
            "failed_criteria": [],
        },
    }

    consensus = eval_dispatch.compute_consensus(verdicts, min_valid_models=2)

    assert "codex" in consensus["objections"]
    assert "claude" in consensus["objections"]
    assert consensus["objections"]["codex"] == ["improve logging"]
    assert consensus["objections"]["claude"] == ["add error handling"]


# ── SensitiveDataMasker ──────────────────────────────────────────


def test_sensitive_data_masker_masks_api_key():
    masker = eval_dispatch.SensitiveDataMasker()
    text = 'api_key = "sk-abcdefghijklmnopqrstuvwxyz1234"'
    masked = masker.mask(text)

    assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in masked
    assert "[MASKED_API_KEY_1]" in masked
    assert masker.masked_count == 1


def test_sensitive_data_masker_masks_connection_string():
    masker = eval_dispatch.SensitiveDataMasker()
    text = 'db_url = "postgres://user:pass@host:5432/db"'
    masked = masker.mask(text)

    assert "postgres://" not in masked
    assert masker.masked_count >= 1


def test_sensitive_data_masker_get_mask_report():
    masker = eval_dispatch.SensitiveDataMasker()
    masker.mask('api_key = "sk-abcdefghijklmnopqrstuvwxyz1234"')
    report = masker.get_mask_report()

    assert len(report) >= 1
    assert report[0]["token"] == "[MASKED_API_KEY_1]"


def test_sensitive_data_masker_same_value_reuses_token():
    masker = eval_dispatch.SensitiveDataMasker()
    text = 'api_key = "sk-abcdefghijklmnopqrstuvwxyz1234"\ntoken = "sk-abcdefghijklmnopqrstuvwxyz1234"'
    masked = masker.mask(text)

    assert masked.count("[MASKED_API_KEY_1]") == 2
    assert masker.masked_count == 1


# ── _build_cmd_string / call_model / _error_json ─────────────────


def test_build_cmd_string_handles_windows_and_posix(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(eval_dispatch, "_IS_WINDOWS", False)
    assert eval_dispatch._build_cmd_string(["echo", "hello world"]) == "echo 'hello world'"

    monkeypatch.setattr(eval_dispatch, "_IS_WINDOWS", True)
    rendered = eval_dispatch._build_cmd_string(["echo", "hello world"])
    assert "hello world" in rendered


def test_call_model_returns_output_file_contents_for_codex(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

    created_path: list[str] = []

    original_mkstemp = eval_dispatch.tempfile.mkstemp

    def fake_mkstemp(**kwargs):
        fd, path = original_mkstemp(dir=str(tmp_path), **kwargs)
        created_path.append(path)
        return fd, path

    def fake_run(*args, **kwargs):
        if created_path:
            Path(created_path[0]).write_text('{"verdict": "pass"}', encoding="utf-8")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(eval_dispatch.tempfile, "mkstemp", fake_mkstemp)
    monkeypatch.setattr(eval_dispatch.subprocess, "run", fake_run)

    assert eval_dispatch.call_model("codex", "prompt") == '{"verdict": "pass"}'


def test_call_model_returns_error_json_on_cli_failure(monkeypatch: pytest.MonkeyPatch):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(eval_dispatch.subprocess, "run", lambda *args, **kwargs: Result())

    response = json.loads(eval_dispatch.call_model("gemini", "prompt"))
    assert response["verdict"] == "error"
    assert "CLI execution failed" in response["error"]


def test_call_model_returns_error_json_when_executable_is_missing(monkeypatch: pytest.MonkeyPatch):
    def raising_run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(eval_dispatch.subprocess, "run", raising_run)

    response = json.loads(eval_dispatch.call_model("claude", "prompt"))
    assert response["verdict"] == "error"
    assert "not found" in response["error"]


def test_call_model_returns_error_on_timeout(monkeypatch: pytest.MonkeyPatch):
    import subprocess as sp

    def raising_run(*args, **kwargs):
        raise sp.TimeoutExpired(cmd="gemini", timeout=10)

    monkeypatch.setattr(eval_dispatch.subprocess, "run", raising_run)

    response = json.loads(eval_dispatch.call_model("gemini", "prompt", timeout=10))
    assert response["verdict"] == "error"
    assert "timeout" in response["error"].lower()


def test_call_model_returns_error_on_generic_exception(monkeypatch: pytest.MonkeyPatch):
    def raising_run(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(eval_dispatch.subprocess, "run", raising_run)

    response = json.loads(eval_dispatch.call_model("claude", "prompt"))
    assert response["verdict"] == "error"
    assert "RuntimeError" in response["error"]


# ── write_result ──────────────────────────────────────────────────


def test_write_result_persists_pretty_json(tmp_path: Path):
    payload = {"verdict": "pass", "issues": []}

    eval_dispatch.write_result(tmp_path, payload)

    written = json.loads((tmp_path / "issues.json").read_text(encoding="utf-8"))
    assert written == payload


# ── load_config ───────────────────────────────────────────────────


def test_load_config_reads_plugin_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = tmp_path / "ahoy_config.json"
    config_path.write_text('{"eval_models": ["codex", "gemini"]}', encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))

    assert eval_dispatch.load_config() == {"eval_models": ["codex", "gemini"]}


# ── main ──────────────────────────────────────────────────────────


def test_main_writes_error_result_when_no_declared_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("AC-001", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text("No files", encoding="utf-8")
    monkeypatch.setattr(
        eval_dispatch.sys,
        "argv",
        ["eval_dispatch.py", str(sprint_dir), "--project-root", str(tmp_path)],
    )

    assert eval_dispatch.main() == 1
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "error"
    assert payload["status_action"] == "error"


def test_main_writes_consensus_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    project_root = tmp_path / "project"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("AC-001", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text(
        "### Files Modified\n- `scripts/example.py`\n",
        encoding="utf-8",
    )
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')", encoding="utf-8")

    def fake_call_model(model: str, prompt: str, timeout: int = 600) -> str:
        assert "Generator Report" in prompt
        return json.dumps(
            {
                "verdict": "pass",
                "issues": [],
                "passed_criteria": ["AC-001"],
                "failed_criteria": [],
                "summary": f"{model} pass",
            }
        )

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        eval_dispatch.sys,
        "argv",
        [
            "eval_dispatch.py",
            str(sprint_dir),
            "--models",
            "codex,claude",
            "--project-root",
            str(project_root),
        ],
    )

    assert eval_dispatch.main() == 0
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "pass"
    assert payload["status_action"] == "passed"
    assert sorted(payload["models_valid"]) == ["claude", "codex"]


def test_main_uses_per_model_prompts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    project_root = tmp_path / "project"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("AC-001", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text(
        "### Files Modified\n- `scripts/example.py`\n",
        encoding="utf-8",
    )
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')", encoding="utf-8")

    captured_prompts: dict[str, str] = {}

    def fake_call_model(model: str, prompt: str, timeout: int = 600) -> str:
        captured_prompts[model] = prompt
        return json.dumps(
            {
                "verdict": "pass",
                "issues": [],
                "passed_criteria": ["AC-001"],
                "failed_criteria": [],
                "summary": f"{model} pass",
            }
        )

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        eval_dispatch,
        "load_config",
        lambda: {
            "eval_models": ["codex", "gemini"],
            "min_models": 2,
            "eval_perspectives": {
                "codex": "accuracy_coverage",
                "gemini": "security_edge",
            },
        },
    )
    monkeypatch.setattr(
        eval_dispatch.sys,
        "argv",
        [
            "eval_dispatch.py",
            str(sprint_dir),
            "--models",
            "codex,gemini",
            "--project-root",
            str(project_root),
        ],
    )

    assert eval_dispatch.main() == 0

    assert "Accuracy & Test Coverage" in captured_prompts["codex"]
    assert "Security & Edge Cases" not in captured_prompts["codex"]
    assert "Security & Edge Cases" in captured_prompts["gemini"]
    assert "Accuracy & Test Coverage" not in captured_prompts["gemini"]


def test_result_includes_model_perspectives(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    project_root = tmp_path / "project"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("AC-001", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text(
        "### Files Modified\n- `scripts/example.py`\n",
        encoding="utf-8",
    )
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')", encoding="utf-8")

    def fake_call_model(model: str, prompt: str, timeout: int = 600) -> str:
        return json.dumps(
            {
                "verdict": "pass",
                "issues": [],
                "passed_criteria": ["AC-001"],
                "failed_criteria": [],
                "summary": f"{model} pass",
            }
        )

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        eval_dispatch,
        "load_config",
        lambda: {
            "eval_models": ["codex", "gemini"],
            "min_models": 2,
            "eval_perspectives": {
                "codex": "accuracy_coverage",
                "gemini": "security_edge",
            },
        },
    )
    monkeypatch.setattr(
        eval_dispatch.sys,
        "argv",
        [
            "eval_dispatch.py",
            str(sprint_dir),
            "--models",
            "codex,gemini",
            "--project-root",
            str(project_root),
        ],
    )

    eval_dispatch.main()
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))

    assert payload["model_perspectives"] == {
        "codex": "accuracy_coverage",
        "gemini": "security_edge",
    }


# ── Backpressure Gate tests ──────────────────────────────────────


def test_parse_eval_strategy_valid(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text(
        '# Spec\n\n```yaml\ntest_command: "uv run pytest"\nlint_command: "ruff check"\n```\n',
        encoding="utf-8",
    )
    result = eval_dispatch.parse_eval_strategy(spec)
    assert result == {"test_command": "uv run pytest"}


def test_parse_eval_strategy_missing_spec(tmp_path: Path):
    result = eval_dispatch.parse_eval_strategy(tmp_path / "nonexistent.md")
    assert result == {}


def test_parse_eval_strategy_malformed(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n\n```yaml\nlint_command: ruff\n```\n", encoding="utf-8")
    result = eval_dispatch.parse_eval_strategy(spec)
    assert result == {}


def test_backpressure_gate_test_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class FakeResult:
        returncode = 0
        stdout = "5 passed"
        stderr = ""

    monkeypatch.setattr(
        eval_dispatch.subprocess, "run",
        lambda *args, **kwargs: FakeResult(),
    )
    result_type, passed, output = eval_dispatch.run_backpressure_gate("pytest", tmp_path)
    assert result_type == "test_result"
    assert passed is True
    assert "5 passed" in output


def test_backpressure_gate_test_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class FakeResult:
        returncode = 1
        stdout = "2 failed, 3 passed"
        stderr = "FAILURES"

    monkeypatch.setattr(
        eval_dispatch.subprocess, "run",
        lambda *args, **kwargs: FakeResult(),
    )
    result_type, passed, output = eval_dispatch.run_backpressure_gate("pytest", tmp_path)
    assert result_type == "test_result"
    assert passed is False
    assert "2 failed" in output


def test_backpressure_gate_infra_cmd_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def raise_fnf(*args, **kwargs):
        raise FileNotFoundError("No such file or directory: 'badcmd'")

    monkeypatch.setattr(eval_dispatch.subprocess, "run", raise_fnf)
    result_type, passed, output = eval_dispatch.run_backpressure_gate("badcmd", tmp_path)
    assert result_type == "infra_error"
    assert passed is False
    assert "command not found" in output


def test_backpressure_gate_infra_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import subprocess as _subprocess

    def raise_timeout(*args, **kwargs):
        raise _subprocess.TimeoutExpired(cmd="pytest", timeout=120)

    monkeypatch.setattr(eval_dispatch.subprocess, "run", raise_timeout)
    result_type, passed, output = eval_dispatch.run_backpressure_gate("pytest", tmp_path, timeout=120)
    assert result_type == "infra_error"
    assert passed is False
    assert "timeout after 120s" in output


def test_backpressure_gate_infra_no_stdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "bash: badcmd: command not found"

    monkeypatch.setattr(
        eval_dispatch.subprocess, "run",
        lambda *args, **kwargs: FakeResult(),
    )
    result_type, passed, output = eval_dispatch.run_backpressure_gate("badcmd", tmp_path)
    assert result_type == "infra_error"
    assert passed is False
    assert "command not found" in output


# --- Cost tracking tests ---


def test_cost_token_estimation():
    """Token estimation is chars // 4."""
    prompt = "x" * 400
    assert len(prompt) // 4 == 100


def test_main_includes_cost_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Full main() produces result with cost_summary."""
    sprint_dir = tmp_path / ".claude" / "harness" / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)

    contract = (
        "## Acceptance Criteria\n"
        "- AC-001: Login endpoint returns 200\n"
        "## Implementation Scope\n"
        "### Files to Create\n"
        "- `src/auth.py`\n"
    )
    (sprint_dir / "contract.md").write_text(contract, encoding="utf-8")

    gen_report = "### Files Created\n- `src/auth.py`\n"
    (sprint_dir / "gen_report.md").write_text(gen_report, encoding="utf-8")

    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text("def login(): return 200\n", encoding="utf-8")

    def fake_call_model(model, prompt, timeout=600):
        return json.dumps({
            "verdict": "pass",
            "objections": ["none"],
            "criteria_results": [{"criterion_id": "AC-001", "verdict": "pass", "evidence": "ok"}],
            "issues": [],
            "passed_criteria": ["AC-001"],
            "failed_criteria": [],
            "summary": "All good",
        })

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude",
         "--project-root", str(tmp_path), "--min-models", "2"],
    )

    exit_code = eval_dispatch.main()
    assert exit_code == 0

    issues = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert "cost_summary" in issues
    cs = issues["cost_summary"]
    assert "entries" in cs
    assert len(cs["entries"]) == 2
    assert cs["total_input_tokens_est"] > 0
    assert cs["total_output_tokens_est"] > 0
    assert cs["wall_duration_s"] >= 0
    for entry in cs["entries"]:
        assert "model" in entry
        assert "input_chars" in entry
        assert "duration_s" in entry
        assert "success" in entry


def test_cost_entry_on_model_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Even when model returns error, cost is still tracked."""
    sprint_dir = tmp_path / ".claude" / "harness" / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)

    contract = "## Acceptance Criteria\n- AC-001: Something\n### Files to Create\n- `src/a.py`\n"
    (sprint_dir / "contract.md").write_text(contract, encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text("### Files Created\n- `src/a.py`\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n", encoding="utf-8")

    def fake_call_model(model, prompt, timeout=600):
        return "unparseable garbage"

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude",
         "--project-root", str(tmp_path), "--min-models", "1"],
    )

    eval_dispatch.main()
    issues = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert "cost_summary" in issues
    for entry in issues["cost_summary"]["entries"]:
        assert entry["success"] is False
        assert entry["duration_s"] >= 0


# --- Deslop scan tests ---


class TestDeslopScan:
    def _setup_sprint(self, tmp_path, file_content, file_name="src/app.py"):
        sprint_dir = tmp_path / ".claude" / "harness" / "sprints" / "sprint-001"
        sprint_dir.mkdir(parents=True)
        gen_report = f"### Files Created\n- `{file_name}`\n"
        (sprint_dir / "gen_report.md").write_text(gen_report, encoding="utf-8")
        src = tmp_path / file_name
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(file_content, encoding="utf-8")
        return sprint_dir

    def test_deslop_detects_debug_print(self, tmp_path):
        sprint_dir = self._setup_sprint(tmp_path, 'def foo():\n    print("debug")\n    return 1\n')
        findings = eval_dispatch.run_deslop_scan(sprint_dir, tmp_path)
        assert len(findings) == 1
        assert findings[0]["pattern"] == "debug_print"
        assert findings[0]["line"] == 2

    def test_deslop_detects_todo_fixme(self, tmp_path):
        sprint_dir = self._setup_sprint(tmp_path, 'x = 1\n# TODO: fix this\ny = 2\n')
        findings = eval_dispatch.run_deslop_scan(sprint_dir, tmp_path)
        assert len(findings) == 1
        assert findings[0]["pattern"] == "todo_fixme"

    def test_deslop_detects_placeholder_pass(self, tmp_path):
        sprint_dir = self._setup_sprint(tmp_path, 'class Foo:\n    pass\n')
        findings = eval_dispatch.run_deslop_scan(sprint_dir, tmp_path)
        assert len(findings) == 1
        assert findings[0]["pattern"] == "placeholder_pass"

    def test_deslop_detects_placeholder_ellipsis(self, tmp_path):
        sprint_dir = self._setup_sprint(tmp_path, 'def bar():\n    ...\n')
        findings = eval_dispatch.run_deslop_scan(sprint_dir, tmp_path)
        assert len(findings) == 1
        assert findings[0]["pattern"] == "placeholder_ellipsis"

    def test_deslop_returns_empty_for_clean_code(self, tmp_path):
        sprint_dir = self._setup_sprint(tmp_path, 'def add(a, b):\n    return a + b\n')
        findings = eval_dispatch.run_deslop_scan(sprint_dir, tmp_path)
        assert findings == []

    def test_deslop_handles_missing_gen_report(self, tmp_path):
        sprint_dir = tmp_path / "sprint-001"
        sprint_dir.mkdir(parents=True)
        findings = eval_dispatch.run_deslop_scan(sprint_dir, tmp_path)
        assert findings == []

    def test_deslop_writes_report_json(self, tmp_path):
        sprint_dir = self._setup_sprint(tmp_path, 'def f():\n    print("x")\n')
        findings = eval_dispatch.run_deslop_scan(sprint_dir, tmp_path)
        assert len(findings) > 0
        report = {"sprint_id": sprint_dir.name, "findings": findings, "total_findings": len(findings)}
        (sprint_dir / "deslop_report.json").write_text(json.dumps(report), encoding="utf-8")
        saved = json.loads((sprint_dir / "deslop_report.json").read_text())
        assert saved["total_findings"] == len(findings)


# --- Contract Drift Detection tests ---


class TestContractDrift:
    def test_parse_contract_file_scope(self):
        contract = (
            "## Implementation Scope\n"
            "### Files to Create\n"
            "- `src/new.py`\n"
            "- `src/helper.py`\n"
            "### Files to Modify\n"
            "- `src/existing.py`\n"
            "### Files to Preserve\n"
            "- `src/keep.py`\n"
        )
        result = eval_dispatch._parse_contract_file_scope(contract)
        assert result == {"src/new.py", "src/helper.py", "src/existing.py"}

    def test_get_git_changed_files(self, monkeypatch):
        def mock_run(cmd, **kwargs):
            import types
            r = types.SimpleNamespace()
            r.returncode = 0
            if "HEAD" in cmd:
                r.stdout = "src/a.py\nsrc/b.py\n"
            elif "--cached" in cmd:
                r.stdout = "src/c.py\n"
            else:
                r.stdout = "src/b.py\nsrc/d.py\n"
            r.stderr = ""
            return r
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = eval_dispatch._get_git_changed_files(Path("/fake"))
        assert result == {"src/a.py", "src/b.py", "src/c.py", "src/d.py"}

    def test_get_git_changed_files_no_git(self, monkeypatch):
        def mock_run(cmd, **kwargs):
            raise FileNotFoundError("git not found")
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = eval_dispatch._get_git_changed_files(Path("/fake"))
        assert result == set()

    def test_get_git_changed_files_filters_noise(self, monkeypatch):
        def mock_run(cmd, **kwargs):
            import types
            r = types.SimpleNamespace()
            r.returncode = 0
            r.stdout = "src/app.py\n__pycache__/foo.pyc\n.claude/harness/state.json\nreal.py\n"
            r.stderr = ""
            return r
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = eval_dispatch._get_git_changed_files(Path("/fake"))
        assert "src/app.py" in result
        assert "real.py" in result
        assert not any("__pycache__" in f for f in result)
        assert not any(".claude" in f for f in result)

    def test_drift_detects_out_of_scope(self, monkeypatch, tmp_path):
        contract = "### Files to Create\n- `src/a.py`\n### Files to Modify\n- `src/b.py`\n"
        monkeypatch.setattr(eval_dispatch, "_get_git_changed_files", lambda root: {"src/a.py", "src/b.py", "src/c.py"})
        sprint_dir = tmp_path / "sprint-001"
        sprint_dir.mkdir()
        drift = eval_dispatch.run_contract_drift_check(contract, sprint_dir, tmp_path)
        assert drift["drift_detected"] is True
        assert "src/c.py" in drift["out_of_scope_files"]
        assert drift["source"] == "git"

    def test_drift_detects_missing_impl(self, monkeypatch, tmp_path):
        contract = "### Files to Create\n- `src/a.py`\n- `src/b.py`\n- `src/c.py`\n"
        monkeypatch.setattr(eval_dispatch, "_get_git_changed_files", lambda root: {"src/a.py"})
        sprint_dir = tmp_path / "sprint-001"
        sprint_dir.mkdir()
        drift = eval_dispatch.run_contract_drift_check(contract, sprint_dir, tmp_path)
        assert drift["drift_detected"] is True
        assert set(drift["missing_impl_files"]) == {"src/b.py", "src/c.py"}

    def test_drift_no_drift_when_aligned(self, monkeypatch, tmp_path):
        contract = "### Files to Create\n- `src/a.py`\n### Files to Modify\n- `src/b.py`\n"
        monkeypatch.setattr(eval_dispatch, "_get_git_changed_files", lambda root: {"src/a.py", "src/b.py"})
        sprint_dir = tmp_path / "sprint-001"
        sprint_dir.mkdir()
        drift = eval_dispatch.run_contract_drift_check(contract, sprint_dir, tmp_path)
        assert drift["drift_detected"] is False

    def test_drift_fallback_to_gen_report(self, monkeypatch, tmp_path):
        contract = "### Files to Create\n- `src/a.py`\n"
        monkeypatch.setattr(eval_dispatch, "_get_git_changed_files", lambda root: set())
        sprint_dir = tmp_path / "sprint-001"
        sprint_dir.mkdir()
        (sprint_dir / "gen_report.md").write_text(
            "### Files Created\n- `src/a.py`\n- `src/extra.py`\n", encoding="utf-8"
        )
        drift = eval_dispatch.run_contract_drift_check(contract, sprint_dir, tmp_path)
        assert drift["source"] == "gen_report"
        assert "src/extra.py" in drift["out_of_scope_files"]
