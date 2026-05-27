from __future__ import annotations

import json
import os
import tempfile
import time
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


def test_collect_code_snippets_uses_git_diff_even_when_gen_report_omits_changed_file(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "gen_report.md").write_text(
        "### Files Modified\n- `scripts/reported.py`\n",
        encoding="utf-8",
    )
    project_root = tmp_path / "project"
    (project_root / "scripts").mkdir(parents=True)
    reported = project_root / "scripts" / "reported.py"
    omitted = project_root / "scripts" / "omitted.py"
    reported.write_text("print('old')\n", encoding="utf-8")
    omitted.write_text("print('missing from report')\n", encoding="utf-8")
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    eval_dispatch.subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "config", "user.name", "Test"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "add", "scripts/reported.py"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "commit", "-m", "base"], cwd=project_root, check=True, capture_output=True, text=True)
    reported.write_text("print('new')\n", encoding="utf-8")

    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root)

    assert "## Git Diff Source of Truth" in snippets
    assert "scripts/reported.py" in snippets
    assert "scripts/omitted.py" in snippets
    assert "print('missing from report')" in snippets
    assert "## Generator Report / Git Mismatch" in snippets
    assert "Changed in git but missing from gen_report.md" in snippets


def test_collect_code_snippets_marks_deleted_renamed_and_truncated_untracked_files(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "gen_report.md").write_text("### Files Modified\n- `keep.txt`\n", encoding="utf-8")
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "deleted.txt").write_text("gone\n", encoding="utf-8")
    (project_root / "old_name.txt").write_text("renamed\n", encoding="utf-8")
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    eval_dispatch.subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "config", "user.name", "Test"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "add", "."], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "commit", "-m", "base"], cwd=project_root, check=True, capture_output=True, text=True)
    (project_root / "deleted.txt").unlink()
    (project_root / "old_name.txt").rename(project_root / "new_name.txt")
    (project_root / "large_untracked.txt").write_text("x" * (eval_dispatch.MAX_DIFF_FILE_BYTES + 1), encoding="utf-8")

    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root)

    assert "deleted.txt" in snippets
    assert "old_name.txt" in snippets
    assert "new_name.txt" in snippets
    assert "large_untracked.txt" in snippets
    assert "[AHOY diff truncated" in snippets


def test_collect_code_snippets_excludes_harness_artifacts_from_git_truth(tmp_path: Path):
    project_root = tmp_path / "project"
    sprint_dir = project_root / ".claude" / "harness" / "sprints" / "sprint-001"
    source_file = project_root / "src" / "feature.py"
    sprint_dir.mkdir(parents=True)
    source_file.parent.mkdir(parents=True)
    (sprint_dir / "gen_report.md").write_text("### Files Modified\n- `src/feature.py`\n", encoding="utf-8")
    source_file.write_text("print('old')\n", encoding="utf-8")
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    eval_dispatch.subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "config", "user.name", "Test"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "add", "src/feature.py"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "commit", "-m", "base"], cwd=project_root, check=True, capture_output=True, text=True)
    source_file.write_text("print('new')\n", encoding="utf-8")
    (sprint_dir / "issues.json").write_text("[]\n", encoding="utf-8")

    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root)

    assert "src/feature.py" in snippets
    assert ".claude/harness" not in snippets
    assert "gen_report.md" not in snippets
    assert "issues.json" not in snippets


def test_collect_code_snippets_uses_git_truth_in_unborn_head_repo(tmp_path: Path):
    project_root = tmp_path / "project"
    sprint_dir = project_root / ".claude" / "harness" / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)
    (sprint_dir / "gen_report.md").write_text("### Files Modified\n- `src/feature.py`\n", encoding="utf-8")
    source_file = project_root / "src" / "feature.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("print('new repo')\n", encoding="utf-8")
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)

    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root)

    assert "## Git Diff Source of Truth" in snippets
    assert "src/feature.py" in snippets
    assert "print('new repo')" in snippets
    assert "fatal: ambiguous argument 'HEAD'" not in snippets


def test_empty_git_tree_falls_back_to_sha1_when_hash_object_fails(monkeypatch, tmp_path: Path):
    def fail_run_git(project_root: Path, args: list[str]):
        return eval_dispatch.subprocess.CompletedProcess(args, 1, "", "hash-object failed")

    monkeypatch.setattr(eval_dispatch, "_run_git", fail_run_git)

    assert eval_dispatch._empty_git_tree(tmp_path) == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def test_parse_porcelain_status_decodes_c_quoted_paths():
    changes = eval_dispatch._parse_porcelain_status('?? "docs/path with spaces.md"\n M "src/quote\\"file.py"\n?? "caf\\303\\251.txt"\n')

    assert changes[0]["path"] == "docs/path with spaces.md"
    assert changes[1]["path"] == 'src/quote"file.py'
    assert changes[2]["path"] == "café.txt"


def test_untracked_file_diff_does_not_follow_symlink_targets(tmp_path: Path):
    target = tmp_path / "outside-secret.txt"
    target.write_text("do not leak\n", encoding="utf-8")
    project_root = tmp_path / "project"
    project_root.mkdir()
    link = project_root / "linked.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    diff = eval_dispatch._untracked_file_diff(project_root, "linked.txt")

    assert "do not leak" not in diff
    assert "[AHOY diff omitted: linked.txt is a symlink]" in diff


def test_filter_source_changes_preserves_source_deletion_when_renamed_into_harness():
    filtered = eval_dispatch._filter_source_changes(
        [
            {
                "status": "R ",
                "type": "renamed",
                "old_path": "src/feature.py",
                "path": ".claude/harness/sprints/sprint-001/feature.py",
            }
        ]
    )

    assert filtered == [{"status": " D", "type": "deleted", "old_path": "", "path": "src/feature.py"}]


def test_report_mismatch_ignores_rename_old_path_when_new_path_is_reported(tmp_path: Path):
    project_root = tmp_path / "project"
    sprint_dir = project_root / ".claude" / "harness" / "sprints" / "sprint-001"
    sprint_dir.mkdir(parents=True)
    (project_root / "src").mkdir()
    old_path = project_root / "src" / "old.py"
    old_path.write_text("print('same')\n", encoding="utf-8")
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    eval_dispatch.subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "config", "user.name", "Test"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "add", "src/old.py"], cwd=project_root, check=True)
    eval_dispatch.subprocess.run(["git", "commit", "-m", "base"], cwd=project_root, check=True, capture_output=True, text=True)
    eval_dispatch.subprocess.run(["git", "mv", "src/old.py", "src/new.py"], cwd=project_root, check=True)
    (sprint_dir / "gen_report.md").write_text("### Files Modified\n- `src/old.py`\n- `src/new.py`\n", encoding="utf-8")

    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root)

    assert "src/old.py" in snippets
    assert "Listed in gen_report.md but not changed in git:\n- `src/old.py`" not in snippets
    assert "Changed in git but missing from gen_report.md:\n- `src/old.py`" not in snippets


def test_collect_git_diff_context_writes_tracked_diff_to_output_file_before_reading(monkeypatch, tmp_path: Path):
    def fake_run_git(project_root: Path, args: list[str]):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "true\n", "")
        if args[-3:] == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, " M tracked.py\n", "")
        if args == ["rev-parse", "--verify", "HEAD"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "abc123\n", "")
        if "diff" in args:
            assert "--no-ext-diff" in args
            output_args = [arg for arg in args if arg.startswith("--output=")]
            assert output_args, f"git diff should write to a file before Python reads/truncates output: {args}"
            Path(output_args[0].split("=", 1)[1]).write_text("diff --git a/tracked.py b/tracked.py\n", encoding="utf-8")
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(eval_dispatch, "_run_git", fake_run_git)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", tempfile.NamedTemporaryFile)

    context = eval_dispatch.collect_git_diff_context(tmp_path, ["tracked.py"])

    assert "diff --git a/tracked.py b/tracked.py" in context


def test_collect_git_diff_context_marks_tracked_diff_truncation(monkeypatch, tmp_path: Path):
    def fake_run_git(project_root: Path, args: list[str]):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "true\n", "")
        if args[-3:] == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, " M tracked.py\n", "")
        if args == ["rev-parse", "--verify", "HEAD"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "abc123\n", "")
        if "diff" in args:
            output_args = [arg for arg in args if arg.startswith("--output=")]
            Path(output_args[0].split("=", 1)[1]).write_text(
                "diff --git a/tracked.py b/tracked.py\n" + ("+x\n" * 100),
                encoding="utf-8",
            )
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(eval_dispatch, "_run_git", fake_run_git)
    monkeypatch.setattr(eval_dispatch, "MAX_DIFF_BYTES", 80)

    context = eval_dispatch.collect_git_diff_context(tmp_path, ["tracked.py"])

    assert "[AHOY diff truncated: tracked git diff exceeded 80 bytes]" in context


def test_collect_git_diff_context_disables_textconv_for_tracked_diff(monkeypatch, tmp_path: Path):
    def fake_run_git(project_root: Path, args: list[str]):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "true\n", "")
        if args[-3:] == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, " M tracked.py\n", "")
        if args == ["rev-parse", "--verify", "HEAD"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "abc123\n", "")
        if "diff" in args:
            assert "--no-textconv" in args
            output_args = [arg for arg in args if arg.startswith("--output=")]
            Path(output_args[0].split("=", 1)[1]).write_text("diff --git a/tracked.py b/tracked.py\n", encoding="utf-8")
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(eval_dispatch, "_run_git", fake_run_git)

    context = eval_dispatch.collect_git_diff_context(tmp_path, ["tracked.py"])

    assert "diff --git a/tracked.py b/tracked.py" in context


def test_collect_git_diff_context_disables_fsmonitor_for_status(monkeypatch, tmp_path: Path):
    def fake_run_git(project_root: Path, args: list[str]):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "true\n", "")
        if "status" in args:
            assert args[:3] == ["-c", "core.fsmonitor=false", "status"]
            return eval_dispatch.subprocess.CompletedProcess(args, 0, " M tracked.py\n", "")
        if args == ["rev-parse", "--verify", "HEAD"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "abc123\n", "")
        if "diff" in args:
            output_args = [arg for arg in args if arg.startswith("--output=")]
            Path(output_args[0].split("=", 1)[1]).write_text("diff --git a/tracked.py b/tracked.py\n", encoding="utf-8")
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(eval_dispatch, "_run_git", fake_run_git)

    context = eval_dispatch.collect_git_diff_context(tmp_path, ["tracked.py"])

    assert "diff --git a/tracked.py b/tracked.py" in context


def test_empty_git_tree_uses_repository_object_format(tmp_path: Path):
    init = eval_dispatch.subprocess.run(
        ["git", "init", "--object-format=sha256"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    if init.returncode != 0:
        pytest.skip("git does not support sha256 repositories")

    expected = eval_dispatch.subprocess.run(
        ["git", "hash-object", "-t", "tree", "/dev/null"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    empty_tree = eval_dispatch._empty_git_tree(tmp_path)

    assert len(empty_tree) == 64
    assert empty_tree == expected


def test_collect_git_diff_context_stops_untracked_diff_collection_at_byte_limit(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def fake_run_git(project_root: Path, args: list[str]):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "true\n", "")
        if args[-3:] == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "?? a.py\n?? b.py\n?? c.py\n", "")
        if args == ["rev-parse", "--verify", "HEAD"]:
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "abc123\n", "")
        if "diff" in args:
            output_args = [arg for arg in args if arg.startswith("--output=")]
            Path(output_args[0].split("=", 1)[1]).write_text("", encoding="utf-8")
            return eval_dispatch.subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    def fake_untracked_file_diff(project_root: Path, rel_path: str) -> str:
        calls.append(rel_path)
        return f"diff --git a/{rel_path} b/{rel_path}\n" + ("x" * 80)

    monkeypatch.setattr(eval_dispatch, "_run_git", fake_run_git)
    monkeypatch.setattr(eval_dispatch, "_untracked_file_diff", fake_untracked_file_diff)
    monkeypatch.setattr(eval_dispatch, "MAX_DIFF_BYTES", 120)

    context = eval_dispatch.collect_git_diff_context(tmp_path, [])

    assert calls == ["a.py", "b.py"]
    assert "[AHOY diff truncated: combined git diff exceeded 120 bytes]" in context
    assert "c.py" not in calls


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


def test_call_model_runs_codex_in_isolated_workspace_without_dangerous_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[dict] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        output_path = tmp_path / ".ahoy-codex-output-1234.txt"
        output_path.write_text('{"verdict": "pass"}', encoding="utf-8")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(eval_dispatch.os, "getpid", lambda: 1234)
    monkeypatch.setattr(eval_dispatch.subprocess, "run", fake_run)

    assert eval_dispatch.call_model("codex", "prompt", workspace=tmp_path) == '{"verdict": "pass"}'

    assert calls[0]["cwd"] == str(tmp_path)
    assert "--dangerously-bypass-approvals-and-sandbox" not in calls[0]["cmd"]


def test_call_model_requires_explicit_opt_in_for_dangerous_codex_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Result:
            returncode = 0
            stdout = '{"verdict": "pass"}'
            stderr = ""

        return Result()

    monkeypatch.setattr(eval_dispatch.subprocess, "run", fake_run)

    eval_dispatch.call_model("codex", "prompt", workspace=tmp_path, allow_dangerous=True)

    assert "--dangerously-bypass-approvals-and-sandbox" in calls[0]


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

    workspaces: list[Path] = []

    def fake_call_model(model: str, prompt: str, timeout: int = 600, **kwargs) -> str:
        assert "Generator Report" in prompt
        workspace = kwargs.get("workspace")
        assert workspace is not None
        workspaces.append(Path(workspace))
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
    assert workspaces
    assert all(project_root not in [workspace, *workspace.parents] for workspace in workspaces)


def test_project_state_detects_git_ignored_file_mutation(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, stdout=eval_dispatch.subprocess.PIPE)
    (project_root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")

    before = eval_dispatch._capture_project_state(project_root)
    (project_root / "ignored.txt").write_text("mutated", encoding="utf-8")
    after = eval_dispatch._capture_project_state(project_root)

    assert eval_dispatch._project_state_changed(before, after)


def test_project_state_detects_git_ignored_content_change_even_if_stat_metadata_is_preserved(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, stdout=eval_dispatch.subprocess.PIPE)
    (project_root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    ignored_path = project_root / "ignored.txt"
    ignored_path.write_text("original", encoding="utf-8")
    original_stat = ignored_path.stat()

    before = eval_dispatch._capture_project_state(project_root)
    ignored_path.write_text("mutated!", encoding="utf-8")
    eval_dispatch.os.utime(ignored_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    after = eval_dispatch._capture_project_state(project_root)

    assert eval_dispatch._project_state_changed(before, after)


def test_project_state_detects_git_metadata_mutation(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    eval_dispatch.subprocess.run(["git", "init"], cwd=project_root, check=True, stdout=eval_dispatch.subprocess.PIPE)

    before = eval_dispatch._capture_project_state(project_root)
    (project_root / ".git" / "ahoy-mutation-marker").write_text("mutated", encoding="utf-8")
    after = eval_dispatch._capture_project_state(project_root)

    assert eval_dispatch._project_state_changed(before, after)


def test_project_state_skips_hashing_special_files(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    fifo_path = project_root / "events.pipe"
    if not hasattr(os, "mkfifo"):
        pytest.skip("fifo files are not available on this platform")
    os.mkfifo(fifo_path)

    state = eval_dispatch._capture_project_state(project_root)

    assert state["files"]["events.pipe"][0] == "special"


def test_project_state_detects_symlink_target_mutation(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_a = tmp_path / "target-a.txt"
    target_b = tmp_path / "target-b.txt"
    target_a.write_text("same content\n", encoding="utf-8")
    target_b.write_text("same content\n", encoding="utf-8")
    link = project_root / "linked.txt"
    try:
        os.symlink(target_a, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    before = eval_dispatch._capture_project_state(project_root)
    link.unlink()
    os.symlink(target_b, link)
    after = eval_dispatch._capture_project_state(project_root)

    assert eval_dispatch._project_state_changed(before, after)


def test_project_state_remains_stable_when_git_status_becomes_unavailable():
    before = {"kind": "workspace", "root": "/repo", "git_status": "", "files": {"a.txt": ("file", 1, 2, "abc")}}
    after = {"kind": "workspace", "root": "/repo", "git_status": None, "files": {"a.txt": ("file", 1, 2, "abc")}}

    assert not eval_dispatch._project_state_changed(before, after)


def test_strict_config_bool_rejects_string_opt_in():
    assert eval_dispatch._strict_config_bool({"allow_dangerous_evaluator_execution": True}, "allow_dangerous_evaluator_execution") is True
    assert eval_dispatch._strict_config_bool({}, "allow_dangerous_evaluator_execution") is False
    with pytest.raises(ValueError):
        eval_dispatch._strict_config_bool(
            {"allow_dangerous_evaluator_execution": "false"},
            "allow_dangerous_evaluator_execution",
        )


def test_main_fails_if_evaluator_mutates_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    project_root = tmp_path / "project"
    sprint_dir.mkdir()
    (sprint_dir / "contract.md").write_text("AC-001", encoding="utf-8")
    (sprint_dir / "gen_report.md").write_text("### Files Modified\n- `scripts/example.py`\n", encoding="utf-8")
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')", encoding="utf-8")

    def mutating_call_model(model: str, prompt: str, timeout: int = 600, **kwargs) -> str:
        (project_root / "evaluator-owned.txt").write_text("mutated", encoding="utf-8")
        return json.dumps({"verdict": "pass", "issues": [], "passed_criteria": ["AC-001"], "failed_criteria": []})

    monkeypatch.setattr(eval_dispatch, "call_model", mutating_call_model)
    monkeypatch.setattr(
        eval_dispatch.sys,
        "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    assert eval_dispatch.main() == 1
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "error"
    assert payload["status_action"] == "error"
    assert "Evaluator modified project workspace" in payload["error_reason"]


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

    def fake_call_model(model: str, prompt: str, timeout: int = 600, **kwargs) -> str:
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


def test_main_round2_skipped_when_cost_limit_exceeded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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
    # Set cost tracking so round-1 preflight passes but round-2 check triggers abort
    # Preflight: 98 + 2 (pending) = 100, NOT > 100 → passes
    # After round-1 tracking: 100 total. Round-2 check: 100 + 2 > 100 → abort
    (harness_dir / "harness_state.json").write_text(
        json.dumps({
            "sprints": [{"sprint_id": "sprint-001", "attempt": 1}],
            "cost_tracking": {"total_eval_calls": 98, "total_tokens": 0, "history": []},
        }),
        encoding="utf-8",
    )

    call_count = {"total": 0}

    def fake_call_model(model: str, prompt: str, timeout: int = 600, **kwargs) -> str:
        call_count["total"] += 1
        # Round 1: conflict to trigger round 2 attempt
        verdict = "fail" if model == "codex" else "pass"
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
        eval_dispatch, "load_config",
        lambda: {"eval_models": ["codex", "claude"], "min_models": 2, "cost_limit": {"max_eval_calls": 100, "max_tokens": 500000}},
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude", "--project-root", str(project_root)],
    )

    eval_dispatch.main()
    payload = json.loads((sprint_dir / "issues.json").read_text(encoding="utf-8"))

    # Round 2 should be skipped due to cost limit — only round 1 calls made
    assert call_count["total"] == 2  # Only round 1 (codex + claude)
    assert payload["evaluation_rounds"] == 1


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

    def fake_call_model(model: str, prompt: str, timeout: int = 600, **kwargs) -> str:
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


def test_parse_eval_strategy(tmp_path: Path):
    config = {"backpressure_gate": {"enabled": True, "test_command": "python -m pytest", "timeout_seconds": 7}}
    missing_spec = tmp_path / "missing.md"

    default_strategy = eval_dispatch.parse_eval_strategy(missing_spec, config)
    assert default_strategy["backpressure_gate"] == {"enabled": True, "test_command": "python -m pytest", "timeout_seconds": 7}

    spec = tmp_path / "spec.md"
    spec.write_text(
        "---\n"
        "backpressure_gate:\n"
        "  enabled: true\n"
        "  test_command: \"python -c 'raise SystemExit(1)'\"\n"
        "  timeout_seconds: 3\n"
        "---\n"
        "# Sprint\n",
        encoding="utf-8",
    )
    parsed = eval_dispatch.parse_eval_strategy(spec, {"backpressure_gate": {"enabled": False}})
    assert parsed["backpressure_gate"]["enabled"] is True
    assert parsed["backpressure_gate"]["test_command"] == "python -c 'raise SystemExit(1)'"
    assert parsed["backpressure_gate"]["timeout_seconds"] == 3

    spec.write_text(
        "---\n"
        "backpressure_gate:\n"
        "  enabled: false # keep disabled due temp regression\n"
        "  test_command: \"echo should_not_run\"\n"
        "---\n",
        encoding="utf-8",
    )
    parsed = eval_dispatch.parse_eval_strategy(spec, {})
    assert parsed["backpressure_gate"]["enabled"] is False

    spec.write_text(
        "---\n"
        "backpressure_gate:\n"
        "  enabled: true # gate can run in CI\n"
        "  test_command: \"echo gate\"\n"
        "---\n",
        encoding="utf-8",
    )
    parsed = eval_dispatch.parse_eval_strategy(spec, {})
    assert parsed["backpressure_gate"]["enabled"] is True

    malformed = tmp_path / "malformed.md"
    malformed.write_text("---\nbackpressure_gate:\n  enabled: [unterminated\n---\n", encoding="utf-8")
    malformed_strategy = eval_dispatch.parse_eval_strategy(malformed, {})
    assert malformed_strategy["backpressure_gate"]["enabled"] is True
    assert malformed_strategy["backpressure_gate"]["result_type"] == "infra_error"
    assert "malformed" in malformed_strategy["backpressure_gate"]["error_reason"].lower()

    quoted_scalar = tmp_path / "quoted.md"
    quoted_scalar.write_text(
        "---\n"
        "backpressure_gate:\n"
        "  enabled: true\n"
        "  test_command: python -m pytest\n"
        "  timeout_seconds: 0.1 # quick gate\n"
        "---\n",
        encoding="utf-8",
    )
    quoted_strategy = eval_dispatch.parse_eval_strategy(quoted_scalar, {})
    assert quoted_strategy["backpressure_gate"]["timeout_seconds"] == "0.1 # quick gate"
    assert eval_dispatch._coerce_timeout(quoted_strategy["backpressure_gate"]["timeout_seconds"]) == 0.1

    quote_error = tmp_path / "quote-error.md"
    quote_error.write_text(
        "---\n"
        "backpressure_gate:\n"
        "  enabled: 'true\n"
        "---\n",
        encoding="utf-8",
    )
    quote_error_strategy = eval_dispatch.parse_eval_strategy(quote_error, {})
    assert quote_error_strategy["backpressure_gate"]["enabled"] is True
    assert quote_error_strategy["backpressure_gate"]["result_type"] == "infra_error"
    assert "unterminated" in quote_error_strategy["backpressure_gate"]["error_reason"].lower()


def test_run_backpressure_gate(tmp_path: Path):
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("ok", encoding="utf-8")

    passed = eval_dispatch.run_backpressure_gate(
        {"enabled": True, "test_command": "python -c \"from pathlib import Path; assert Path('sentinel.txt').exists(); print('pass-out')\"", "timeout_seconds": 5},
        tmp_path,
    )
    assert passed["result_type"] == "test_result"
    assert passed["verdict"] == "pass"
    assert passed["status_action"] == "passed"
    assert passed["exit_code"] == 0
    assert "pass-out" in passed["stdout"]
    assert passed["stderr"] == ""

    failed = eval_dispatch.run_backpressure_gate(
        {"enabled": True, "test_command": "python -c \"import sys; print('fail-out'); sys.exit(1)\"", "timeout_seconds": 5},
        tmp_path,
    )
    assert failed["result_type"] == "test_result"
    assert failed["verdict"] == "fail"
    assert failed["status_action"] == "failed"
    assert failed["exit_code"] == 1
    assert "fail-out" in failed["stdout"]

    stderr_only = eval_dispatch.run_backpressure_gate(
        {"enabled": True, "test_command": "python -c \"import sys; print('stderr-only', file=sys.stderr)\"", "timeout_seconds": 5},
        tmp_path,
    )
    assert stderr_only["result_type"] == "test_result"
    assert stderr_only["verdict"] == "pass"
    assert stderr_only["stdout"] == ""
    assert "stderr-only" in stderr_only["stderr"]

    shell_semantics = eval_dispatch.run_backpressure_gate(
        {
            "enabled": True,
            "test_command": (
                "AHOY_GATE=ok python -c \"import os; print(os.environ['AHOY_GATE'])\" "
                "> shell-out.txt && test -s shell-out.txt"
            ),
            "timeout_seconds": 5,
        },
        tmp_path,
    )
    assert shell_semantics["result_type"] == "test_result"
    assert shell_semantics["verdict"] == "pass"
    assert (tmp_path / "shell-out.txt").read_text(encoding="utf-8").strip() == "ok"

    missing = eval_dispatch.run_backpressure_gate(
        {"enabled": True, "test_command": "definitely-not-a-real-ahoy-command", "timeout_seconds": 5},
        tmp_path,
    )
    assert missing["result_type"] == "infra_error"
    assert missing["verdict"] == "error"
    assert missing["status_action"] == "error"
    assert missing["exit_code"] == 2

    timeout_start = time.monotonic()
    timeout = eval_dispatch.run_backpressure_gate(
        {
            "enabled": True,
            "test_command": (
                "python -c \"import subprocess, time; "
                "subprocess.Popen(['python', '-c', 'import time; time.sleep(10)']); "
                "time.sleep(10)\""
            ),
            "timeout_seconds": 0.1,
        },
        tmp_path,
    )
    elapsed = time.monotonic() - timeout_start
    assert timeout["result_type"] == "infra_error"
    assert timeout["verdict"] == "error"
    assert timeout["status_action"] == "error"
    assert timeout["exit_code"] == 2
    assert "timeout" in timeout["error_reason"].lower()
    assert elapsed < 3
