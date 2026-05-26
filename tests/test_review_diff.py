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
    assert not (tmp_path / ".claude" / "harness").exists()


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

    assert review_diff.main() == 0
    payload = json.loads((tmp_path / "review.md.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "strict"


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
