from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import load_module

eval_dispatch = load_module("test_eval_dispatch_module", "scripts/eval_dispatch.py")


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


def test_extract_json_reads_fenced_and_embedded_payloads():
    fenced = "```json\n{\"verdict\": \"pass\"}\n```"
    embedded = 'prefix {"verdict": "fail", "issues": []} suffix'

    assert eval_dispatch.extract_json(fenced) == {"verdict": "pass"}
    assert eval_dispatch.extract_json(embedded) == {"verdict": "fail", "issues": []}


def test_extract_json_returns_none_for_invalid_payload():
    assert eval_dispatch.extract_json("no json here") is None


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
        "codex": "partial_pass",
        "claude": "fail",
        "gemini": "error",
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


def test_write_result_persists_pretty_json(tmp_path: Path):
    payload = {"verdict": "pass", "issues": []}

    eval_dispatch.write_result(tmp_path, payload)

    written = json.loads((tmp_path / "issues.json").read_text(encoding="utf-8"))
    assert written == payload


def test_build_cmd_string_handles_windows_and_posix(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(eval_dispatch, "_IS_WINDOWS", False)
    assert eval_dispatch._build_cmd_string(["echo", "hello world"]) == "echo 'hello world'"

    monkeypatch.setattr(eval_dispatch, "_IS_WINDOWS", True)
    rendered = eval_dispatch._build_cmd_string(["echo", "hello world"])
    assert "hello world" in rendered


def test_call_model_returns_output_file_contents_for_codex(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

    def fake_run(*args, **kwargs):
        output_path = tmp_path / ".ahoy-codex-output-1234.txt"
        output_path.write_text('{"verdict": "pass"}', encoding="utf-8")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(eval_dispatch.os, "getpid", lambda: 1234)
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


def test_load_config_reads_plugin_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = tmp_path / "ahoy_config.json"
    config_path.write_text('{"eval_models": ["codex", "gemini"]}', encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))

    assert eval_dispatch.load_config() == {"eval_models": ["codex", "gemini"]}


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
    assert payload["models_valid"] == ["codex", "claude"]
