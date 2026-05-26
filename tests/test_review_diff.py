from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import load_module

review_diff = load_module("test_review_diff_module", "scripts/review_diff.py")


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "tracked.txt").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=path, check=True)


def fake_evaluator(path: Path, verdict: str = "pass") -> str:
    path.write_text(
        "import json, sys\n"
        "prompt = sys.stdin.read()\n"
        "assert '## Git Diff' in prompt\n"
        "print(json.dumps({\n"
        f"  'verdict': {verdict!r},\n"
        "  'objections': ['check edge cases'],\n"
        "  'issues': [],\n"
        "  'passed_criteria': ['DIFF-REVIEW'],\n"
        "  'failed_criteria': [],\n"
        "  'summary': 'fake review complete',\n"
        "  'reasoning_chain': {\n"
        "    'code_understanding': 'diff read',\n"
        "    'ac_verification': 'reviewed changed lines',\n"
        "    'quality_assessment': 'ok',\n"
        "    'final_reasoning': 'pass'\n"
        "  }\n"
        "}))\n",
        encoding="utf-8",
    )
    return f"python {path}"


def test_review_diff_reports_no_diff_without_creating_harness_state(tmp_path: Path):
    init_repo(tmp_path)

    result = review_diff.run_review_diff(tmp_path, mode="advisory", models=["fake"], evaluator_command="python -c 'raise SystemExit(99)'", report_path=tmp_path / "review.md")

    assert result["status"] == "no_diff"
    assert result["verdict"] == "no_diff"
    assert "no git diff" in result["summary"].lower()
    assert result["report_path"] == str(tmp_path / "review.md")
    assert (tmp_path / "review.md").exists()
    assert (tmp_path / "review.md.json").exists()
    assert not (tmp_path / ".claude" / "harness").exists()


def test_review_diff_includes_untracked_files_in_prompt(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "new_feature.py").write_text("print('new')\n", encoding="utf-8")
    command = fake_evaluator(tmp_path.parent / "fake_eval_untracked.py")

    result = review_diff.run_review_diff(tmp_path, mode="advisory", models=["fake"], evaluator_command=command, report_path=tmp_path / "review.md")

    assert result["status"] == "passed"
    assert result["diff_summary"]["files_changed"] == ["new_feature.py"]
    assert result["diff_summary"]["additions"] == 1


def test_review_diff_handles_unborn_head_repo_with_untracked_file(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "first.txt").write_text("first\n", encoding="utf-8")
    command = fake_evaluator(tmp_path.parent / "fake_eval_unborn.py")

    result = review_diff.run_review_diff(tmp_path, mode="advisory", models=["fake"], evaluator_command=command, report_path=tmp_path / "review.md")

    assert result["status"] == "passed"
    assert "first.txt" in result["diff_summary"]["files_changed"]


def test_review_diff_includes_unstaged_hunks_when_head_is_unborn(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "first.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "first.txt"], cwd=tmp_path, check=True)
    (tmp_path / "first.txt").write_text("staged\nunstaged\n", encoding="utf-8")
    command = fake_evaluator(tmp_path.parent / "fake_eval_unborn_unstaged.py")

    result = review_diff.run_review_diff(tmp_path, mode="advisory", models=["fake"], evaluator_command=command, report_path=tmp_path / "review.md")

    assert result["status"] == "passed"
    assert result["diff_summary"]["files_changed"] == ["first.txt"]
    assert result["diff_summary"]["additions"] == 2


def test_review_diff_summary_handles_paths_with_spaces(tmp_path: Path):
    summary = review_diff._diff_summary(
        "diff --git a/path with spaces.txt b/path with spaces.txt\n"
        "+++ b/path with spaces.txt\n"
        "+new line\n"
    )

    assert summary["files_changed"] == ["path with spaces.txt"]


def test_review_diff_summary_handles_quoted_diff_headers(tmp_path: Path):
    summary = review_diff._diff_summary(
        'diff --git "a/docs/한글 파일.md" "b/docs/한글 파일.md"\n'
        '+++ "b/docs/한글 파일.md"\n'
        "+new line\n"
    )

    assert summary["files_changed"] == ["docs/한글 파일.md"]


def test_review_diff_normalizes_uppercase_failure_verdict(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    command = fake_evaluator(tmp_path / "fake_eval_upper_fail.py", verdict="FAIL")

    result = review_diff.run_review_diff(tmp_path, mode="advisory", models=["fake"], evaluator_command=command, report_path=tmp_path / "review.md")

    assert result["verdict"] == "fail"
    assert result["status"] == "failed"
    assert result["models_valid"] == ["fake"]


def test_review_diff_treats_missing_verdict_as_model_error_without_aborting_valid_advisory_model(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    evaluator = tmp_path / "mixed_eval.py"
    evaluator.write_text(
        "import json, os, sys\n"
        "sys.stdin.read()\n"
        "if os.environ['AHOY_REVIEW_DIFF_MODEL'] == 'bad':\n"
        "    print(json.dumps({'summary': 'missing verdict'}))\n"
        "else:\n"
        "    print(json.dumps({'verdict': 'pass', 'objections': ['ok'], 'issues': [], 'passed_criteria': ['DIFF-REVIEW'], 'failed_criteria': [], 'summary': 'good'}))\n",
        encoding="utf-8",
    )

    result = review_diff.run_review_diff(
        tmp_path,
        mode="advisory",
        models=["bad", "good"],
        evaluator_command=f"python {evaluator}",
        min_models=1,
        report_path=tmp_path / "review.md",
    )

    assert result["status"] == "passed"
    assert result["models_valid"] == ["good"]
    assert result["model_verdicts"]["bad"]["verdict"] == "error"


def test_review_diff_cli_uses_existing_cwd_for_relative_error_report_when_project_root_is_missing(tmp_path: Path, monkeypatch, capsys):
    missing_root = tmp_path / "does-not-exist"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        review_diff.sys,
        "argv",
        ["review_diff.py", "--project-root", str(missing_root), "--report", "out.md"],
    )

    assert review_diff.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["report_path"] == str(tmp_path / "out.md")
    assert (tmp_path / "out.md").exists()
    assert (tmp_path / "out.md.json").exists()


def test_review_diff_rejects_non_integer_config_min_models_with_clear_error(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    (tmp_path / "ahoy_config.json").write_text(json.dumps({"eval_models": ["fake"], "min_models": "two"}), encoding="utf-8")

    try:
        review_diff.run_review_diff(tmp_path, mode="strict", evaluator_command="python -c 'raise SystemExit(99)'", report_path=tmp_path / "review.md")
    except ValueError as exc:
        assert "min_models must be an integer" in str(exc)
    else:
        raise AssertionError("expected invalid min_models config to raise ValueError")


def test_review_diff_rejects_non_string_config_eval_models_with_clear_error(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    (tmp_path / "ahoy_config.json").write_text(json.dumps({"eval_models": ["fake", 42], "min_models": 1}), encoding="utf-8")

    try:
        review_diff.run_review_diff(tmp_path, mode="advisory", evaluator_command="python -c 'raise SystemExit(99)'", report_path=tmp_path / "review.md")
    except ValueError as exc:
        assert "eval_models entries must be strings" in str(exc)
    else:
        raise AssertionError("expected invalid eval_models config to raise ValueError")


def test_review_diff_strict_mode_keeps_two_model_minimum_even_with_explicit_one(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    command = fake_evaluator(tmp_path / "fake_eval.py")

    result = review_diff.run_review_diff(tmp_path, mode="strict", models=["fake"], evaluator_command=command, min_models=1, report_path=tmp_path / "review.md")

    assert result["status"] == "error"
    assert result["min_models"] == 2


def test_review_diff_cli_returns_structured_error_for_runtime_failures(tmp_path: Path, monkeypatch, capsys):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    (tmp_path / "ahoy_config.json").write_text(json.dumps({"eval_models": [42], "min_models": 1}), encoding="utf-8")
    monkeypatch.setattr(
        review_diff.sys,
        "argv",
        ["review_diff.py", "--project-root", str(tmp_path), "--report", str(tmp_path / "review.md")],
    )

    assert review_diff.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert "eval_models entries must be strings" in payload["error_reason"]


def test_review_diff_advisory_mode_accepts_one_evaluator_and_writes_report(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    command = fake_evaluator(tmp_path / "fake_eval.py")

    result = review_diff.run_review_diff(tmp_path, mode="advisory", models=["fake"], evaluator_command=command, report_path=tmp_path / "review.md")

    assert result["status"] == "passed"
    assert result["mode"] == "advisory"
    assert result["models_valid"] == ["fake"]
    assert result["min_models"] == 1
    report = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "# AHOY Review Diff Report" in report
    assert "fake review complete" in report
    assert not (tmp_path / ".claude" / "harness").exists()


def test_review_diff_strict_mode_fails_closed_when_quorum_is_unavailable(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    command = fake_evaluator(tmp_path / "fake_eval.py")

    result = review_diff.run_review_diff(tmp_path, mode="strict", models=["fake"], evaluator_command=command, min_models=2, report_path=tmp_path / "review.md")

    assert result["status"] == "error"
    assert result["verdict"] == "error"
    assert result["min_models"] == 2
    assert "minimum 2 required" in result["error_reason"]


def test_review_diff_relative_report_path_is_resolved_under_project_root(tmp_path: Path):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    command = fake_evaluator(tmp_path / "fake_eval.py")

    result = review_diff.run_review_diff(tmp_path, mode="advisory", models=["fake"], evaluator_command=command, report_path=Path("review.md"))

    assert result["status"] == "passed"
    assert result["report_path"] == str(tmp_path / "review.md")
    assert (tmp_path / "review.md").exists()
    assert (tmp_path / "review.md.json").exists()


def test_review_diff_cli_accepts_strict_shortcut_flag(tmp_path: Path, monkeypatch):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    command = fake_evaluator(tmp_path / "fake_eval.py")
    monkeypatch.setattr(
        review_diff.sys,
        "argv",
        [
            "review_diff.py",
            "--project-root",
            str(tmp_path),
            "--strict",
            "--models",
            "fake",
            "--min-models",
            "1",
            "--evaluator-command",
            command,
            "--report",
            str(tmp_path / "review.md"),
        ],
    )

    assert review_diff.main() == 2
    payload = json.loads((tmp_path / "review.md.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "strict"
    assert payload["min_models"] == 2


def test_review_diff_cli_emits_json_for_advisory(tmp_path: Path, monkeypatch):
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    command = fake_evaluator(tmp_path / "fake_eval.py")
    monkeypatch.setattr(
        review_diff.sys,
        "argv",
        [
            "review_diff.py",
            "--project-root",
            str(tmp_path),
            "--mode",
            "advisory",
            "--models",
            "fake",
            "--evaluator-command",
            command,
            "--report",
            str(tmp_path / "review.md"),
        ],
    )

    assert review_diff.main() == 0
    payload = json.loads((tmp_path / "review.md.json").read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
