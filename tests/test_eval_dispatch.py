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


def test_validate_objections_normalizes_non_empty_strings():
    parsed = {"verdict": "pass", "objections": [" one ", "", 3]}

    validated = eval_dispatch.validate_objections(parsed, "codex")

    assert validated["objections"] == [" one "]


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


def test_check_verdict_conflict_detects_hard_disagreement():
    assert eval_dispatch.check_verdict_conflict(
        {
            "codex": {"verdict": "pass"},
            "claude": {"verdict": "fail"},
            "gemini": {"verdict": "error"},
        }
    )
    assert not eval_dispatch.check_verdict_conflict(
        {
            "codex": {"verdict": "pass"},
            "claude": {"verdict": "partial_pass"},
        }
    )


def test_build_round2_prompt_includes_round1_summaries():
    prompt = eval_dispatch.build_round2_prompt(
        "BASE",
        {
            "codex": {"verdict": "fail", "summary": "bad", "issues": [{"severity": "major", "description": "oops"}]},
            "claude": {"verdict": "error"},
        },
    )

    assert "Round 2" in prompt
    assert "### codex" in prompt
    assert "oops" in prompt
    assert "### claude" not in prompt


def test_parse_usage_prefers_embedded_usage_and_falls_back_to_estimate():
    parsed = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    assert eval_dispatch.parse_usage("ignored", parsed=parsed) == {"input_tokens": 10, "output_tokens": 5}
    assert eval_dispatch.parse_usage("12345678", parsed=None) == {"input_tokens": 0, "output_tokens": 2}


def test_update_cost_tracking_and_limit_checks(tmp_path: Path):
    harness_state = tmp_path / "harness_state.json"

    eval_dispatch.update_cost_tracking(harness_state, eval_calls=2, tokens=100, sprint_id="sprint-001", attempt=1)
    payload = json.loads(harness_state.read_text(encoding="utf-8"))

    assert payload["cost_tracking"]["total_eval_calls"] == 2
    assert payload["cost_tracking"]["total_tokens"] == 100
    assert payload["cost_tracking"]["history"][0]["sprint_id"] == "sprint-001"
    assert eval_dispatch.check_cost_limit(
        harness_state,
        {"cost_limit": {"max_eval_calls": 1, "max_tokens": 1000}},
        pending_calls=0,
    )
    assert eval_dispatch.check_cost_limit(
        harness_state,
        {"cost_limit": {"max_eval_calls": 5, "max_tokens": 50}},
        pending_calls=0,
    )
    assert not eval_dispatch.check_cost_limit(
        harness_state,
        {"cost_limit": {"max_eval_calls": 5, "max_tokens": 200}},
        pending_calls=1,
    )


def test_record_convergence_updates_matching_sprint(tmp_path: Path):
    project_root = tmp_path / "project"
    sprint_dir = project_root / ".claude" / "harness" / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)
    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state_file.write_text(
        json.dumps({"sprints": [{"sprint_id": "sprint-001", "attempt": 2}]}),
        encoding="utf-8",
    )

    eval_dispatch._record_convergence(sprint_dir, project_root, 0.75)

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["sprints"][0]["convergence_history"][0]["convergence_ratio"] == 0.75


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

    assert eval_dispatch.load_config() == {"eval_models": ["codex", "gemini"], "cost_limit": None}


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


def test_main_aborts_when_cost_limit_is_exceeded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("AC-001", encoding="utf-8")
    harness_state = tmp_path / ".claude" / "harness"
    harness_state.mkdir(parents=True)
    (harness_state / "harness_state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(eval_dispatch, "load_config", lambda: {"eval_models": ["codex"], "min_models": 1, "cost_limit": {"max_eval_calls": 0}})
    monkeypatch.setattr(
        eval_dispatch.sys,
        "argv",
        ["eval_dispatch.py", str(sprint_dir), "--project-root", str(tmp_path)],
    )

    assert eval_dispatch.main() == 1
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["error_reason"] == "Cost limit exceeded"


def test_main_uses_round2_when_round1_has_conflict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    project_root = tmp_path / "project"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("## Acceptance Criteria\n- AC-1: works", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text("### Files Modified\n- `scripts/example.py`\n", encoding="utf-8")
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')", encoding="utf-8")
    harness_dir = project_root / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps({"sprints": [{"sprint_id": "sprint-001", "attempt": 1}]}),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_call_model(model: str, prompt: str, timeout: int = 600) -> str:
        calls.append(prompt)
        round_number = len(calls) // 2 + (1 if len(calls) % 2 else 0)
        if "Round 2" not in prompt:
            verdict = "fail" if model == "codex" else "pass"
        else:
            verdict = "partial_pass"
        return json.dumps(
            {
                "verdict": verdict,
                "objections": ["improve docs"],
                "criteria_results": [
                    {"criterion_id": "AC-1", "description": "works", "verdict": "pass", "evidence": "ok"}
                ],
                "issues": [],
                "passed_criteria": ["AC-1"],
                "failed_criteria": [],
                "summary": f"{model} round {round_number}",
                "reasoning_chain": {
                    "code_understanding": "a",
                    "ac_verification": "b",
                    "quality_assessment": "c",
                    "final_reasoning": "d",
                },
            }
        )

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        eval_dispatch.sys,
        "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    assert eval_dispatch.main() == 0
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["evaluation_rounds"] == 2
    assert payload["round2_verdicts"] == {"codex": "partial_pass", "claude": "partial_pass"}
    assert payload["convergence_ratio"] == 1.0


# ── v0.2.0 gap-fill tests ───────────────────────────────────────


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


def test_validate_objections_skips_error_verdicts():
    parsed = {"verdict": "error", "error": "CLI failed"}

    validated = eval_dispatch.validate_objections(parsed, "codex")

    assert validated == parsed


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


def test_record_convergence_skips_missing_sprint(tmp_path: Path):
    project_root = tmp_path / "project"
    sprint_dir = project_root / ".claude" / "harness" / "sprints" / "sprint-999"
    sprint_dir.mkdir(parents=True)
    state_file = project_root / ".claude" / "harness" / "harness_state.json"
    state_file.write_text(
        json.dumps({"sprints": [{"sprint_id": "sprint-001", "attempt": 1}]}),
        encoding="utf-8",
    )

    eval_dispatch._record_convergence(sprint_dir, project_root, 0.5)

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert "convergence_history" not in payload["sprints"][0]


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


def test_warn_if_missing_reasoning_chain_logs_warnings(capsys: pytest.CaptureFixture[str]):
    eval_dispatch._warn_if_missing_reasoning_chain("codex", {"verdict": "pass"})
    assert "missing reasoning_chain" in capsys.readouterr().err

    eval_dispatch._warn_if_missing_reasoning_chain("codex", {"verdict": "pass", "reasoning_chain": "not-a-dict"})
    assert "not a dict" in capsys.readouterr().err

    eval_dispatch._warn_if_missing_reasoning_chain(
        "codex", {"verdict": "pass", "reasoning_chain": {"code_understanding": "a"}}
    )
    assert "incomplete" in capsys.readouterr().err


def test_main_round2_quorum_lost_falls_back_to_round1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    project_root = tmp_path / "project"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("## Acceptance Criteria\n- AC-1: works", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text("### Files Modified\n- `scripts/example.py`\n", encoding="utf-8")
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')", encoding="utf-8")
    harness_dir = project_root / ".claude" / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "harness_state.json").write_text(
        json.dumps({"sprints": [{"sprint_id": "sprint-001", "attempt": 1}]}),
        encoding="utf-8",
    )

    call_count = {"total": 0}

    def fake_call_model(model: str, prompt: str, timeout: int = 600) -> str:
        call_count["total"] += 1
        if "Round 2" not in prompt:
            # Round 1: conflict
            verdict = "fail" if model == "codex" else "pass"
        else:
            # Round 2: codex errors out -> quorum lost
            if model == "codex":
                return json.dumps({"verdict": "error", "error": "timeout"})
            verdict = "pass"
        return json.dumps({
            "verdict": verdict,
            "objections": ["nit"],
            "criteria_results": [{"criterion_id": "AC-1", "description": "works", "verdict": "pass", "evidence": "ok"}],
            "issues": [{"id": "ISS-1", "severity": "minor", "description": "nit"}] if verdict == "fail" else [],
            "passed_criteria": ["AC-1"] if verdict == "pass" else [],
            "failed_criteria": ["AC-1"] if verdict == "fail" else [],
            "summary": f"{model} verdict",
        })

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    exit_code = eval_dispatch.main()
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))

    assert payload["evaluation_rounds"] == 2
    # Round 2 quorum lost -> falls back to round 1, which had a fail -> final fail
    assert payload["verdict"] == "fail"
    assert exit_code == 1
