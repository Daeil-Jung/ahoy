#!/usr/bin/env python3
"""Lightweight git-diff review workflow for AHOY.

This path reviews the current git diff without creating or mutating sprint harness
state. It is intentionally smaller than the full /ahoy sprint workflow.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_eval_dispatch():
    module_path = Path(__file__).with_name("eval_dispatch.py")
    spec = importlib.util.spec_from_file_location("ahoy_eval_dispatch_for_review_diff", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load eval_dispatch.py from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("ahoy_eval_dispatch_for_review_diff", module)
    spec.loader.exec_module(module)
    return module


eval_dispatch = _load_eval_dispatch()

VALID_MODES = {"advisory", "strict"}
DEFAULT_REPORT = "ahoy_review_diff_report.md"


def load_config(project_root: Path) -> dict:
    config_path = project_root / "ahoy_config.json"
    if not config_path.exists():
        return {"eval_models": ["codex", "claude"], "min_models": 2}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"eval_models": ["codex", "claude"], "min_models": 2}
    config.setdefault("eval_models", ["codex", "claude"])
    config.setdefault("min_models", 2)
    return config


def collect_git_diff(project_root: Path) -> str:
    """Return staged+unstaged diff against HEAD, with no color or external diff."""
    result = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--no-color", "HEAD", "--"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return result.stdout


def _diff_summary(diff_text: str) -> dict:
    files: list[str] = []
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                path = parts[3]
                files.append(path[2:] if path.startswith("b/") else path)
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return {
        "files_changed": list(dict.fromkeys(files)),
        "file_count": len(list(dict.fromkeys(files))),
        "additions": additions,
        "deletions": deletions,
    }


def build_review_prompt(diff_text: str, mode: str, summary: dict) -> str:
    return f"""You are an independent external reviewer for AHOY's lightweight review-diff workflow.

Review the current git diff only. Do not infer hidden sprint state, generator reports, or user intent outside this diff.

## Review Mode
{mode}

## Diff Summary
- Files changed: {summary.get('file_count', 0)}
- Additions: {summary.get('additions', 0)}
- Deletions: {summary.get('deletions', 0)}
- Paths: {', '.join(summary.get('files_changed', [])) or '(none)'}

## Review Criteria
- Correctness and likely runtime failures
- Tests or verification gaps for changed behavior
- Security and data-loss risks
- Maintainability and avoidable complexity

## Git Diff
```diff
{diff_text}
```

Respond ONLY as JSON:
{{
  "verdict": "pass" | "partial_pass" | "fail",
  "objections": ["at least one concrete concern or improvement"],
  "issues": [
    {{
      "id": "DIFF-001",
      "severity": "blocker" | "major" | "minor",
      "category": "functional" | "test" | "quality" | "security" | "performance",
      "description": "specific issue",
      "suggested_fix": "specific fix direction"
    }}
  ],
  "passed_criteria": ["DIFF-REVIEW"],
  "failed_criteria": [],
  "summary": "one-line review summary",
  "reasoning_chain": {{
    "code_understanding": "what changed",
    "ac_verification": "how the diff meets or misses review criteria",
    "quality_assessment": "quality/security/performance assessment",
    "final_reasoning": "why this verdict was chosen"
  }}
}}
"""


def _run_evaluator_command(command: str, prompt: str, cwd: Path, model: str, timeout: int) -> str:
    env = os.environ.copy()
    env["AHOY_REVIEW_DIFF_MODEL"] = model
    result = subprocess.run(
        command,
        input=prompt,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        shell=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0 and not result.stdout.strip():
        return json.dumps({
            "verdict": "error",
            "error": f"evaluator command failed (exit {result.returncode}): {result.stderr[:300]}",
            "issues": [],
            "passed_criteria": [],
            "failed_criteria": [],
            "summary": f"{model} review failed",
        })
    return result.stdout


def call_reviewer(model: str, prompt: str, project_root: Path, evaluator_command: str | None, timeout: int) -> tuple[str, dict, str]:
    try:
        raw = (
            _run_evaluator_command(evaluator_command, prompt, project_root, model, timeout)
            if evaluator_command
            else eval_dispatch.call_model(model, prompt, timeout=timeout)
        )
    except subprocess.TimeoutExpired:
        raw = json.dumps({"verdict": "error", "error": f"timeout after {timeout}s", "summary": f"{model} review failed"})
    parsed = eval_dispatch.extract_json(raw)
    if parsed is None:
        parsed = {
            "verdict": "error",
            "error": f"JSON parsing failed. Raw: {raw[:300]}",
            "issues": [],
            "passed_criteria": [],
            "failed_criteria": [],
            "summary": "Response parsing failed",
        }
    else:
        parsed = eval_dispatch.validate_objections(parsed, model)
    return model, parsed, raw


def mode_min_models(mode: str, configured_min: int, explicit_min: int | None) -> int:
    if explicit_min is not None:
        return explicit_min
    if mode == "advisory":
        return 1
    return max(2, int(configured_min or 2))


def render_report(result: dict) -> str:
    lines = [
        "# AHOY Review Diff Report",
        "",
        f"- Mode: {result.get('mode')}",
        f"- Verdict: {result.get('verdict')}",
        f"- Status: {result.get('status')}",
        f"- Models valid: {', '.join(result.get('models_valid', [])) or '(none)'}",
        f"- Files changed: {result.get('diff_summary', {}).get('file_count', 0)}",
        "",
        "## Summary",
        result.get("summary", ""),
        "",
    ]
    if result.get("error_reason"):
        lines.extend(["## Error", result["error_reason"], ""])
    if result.get("issues"):
        lines.append("## Issues")
        for issue in result["issues"]:
            lines.append(f"- [{issue.get('severity', '?')}] {issue.get('id', '?')}: {issue.get('description', '')}")
            if issue.get("suggested_fix"):
                lines.append(f"  - Fix: {issue['suggested_fix']}")
        lines.append("")
    if result.get("objections"):
        lines.append("## Objections")
        objections = result["objections"]
        if isinstance(objections, dict):
            for model, items in objections.items():
                for item in items:
                    lines.append(f"- {model}: {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_review_diff(
    project_root: Path,
    mode: str = "advisory",
    models: list[str] | None = None,
    evaluator_command: str | None = None,
    min_models: int | None = None,
    report_path: Path | None = None,
    timeout: int = 600,
) -> dict:
    project_root = project_root.resolve()
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
    config = load_config(project_root)
    selected_models = [m.strip() for m in (models or config.get("eval_models", ["codex", "claude"])) if m.strip()]
    minimum = mode_min_models(mode, int(config.get("min_models", 2)), min_models)
    report_path = report_path or (project_root / DEFAULT_REPORT)
    if not report_path.is_absolute():
        report_path = project_root / report_path

    diff_text = collect_git_diff(project_root)
    summary = _diff_summary(diff_text)
    if not diff_text.strip():
        return {
            "workflow": "review-diff",
            "mode": mode,
            "status": "no_diff",
            "verdict": "no_diff",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "models_used": [],
            "models_valid": [],
            "min_models": minimum,
            "diff_summary": summary,
            "summary": "No git diff to review.",
        }

    prompt = build_review_prompt(diff_text, mode, summary)
    verdicts: dict[str, dict] = {}
    for model in selected_models:
        model_name, parsed, _raw = call_reviewer(model, prompt, project_root, evaluator_command, timeout)
        verdicts[model_name] = parsed

    consensus = eval_dispatch.compute_consensus(verdicts, min_valid_models=minimum)
    issues = consensus.get("issues", [])
    verdict = consensus["consensus_verdict"]
    status = eval_dispatch.derive_status_action(verdict, issues)
    result = {
        "workflow": "review-diff",
        "mode": mode,
        "status": status,
        "verdict": verdict,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "models_used": selected_models,
        "models_valid": [k for k, v in verdicts.items() if v.get("verdict") != "error"],
        "min_models": minimum,
        "diff_summary": summary,
        "model_verdicts": consensus.get("model_verdicts", {}),
        "issues": issues,
        "objections": consensus.get("objections", {}),
        "passed_criteria": consensus.get("passed_criteria", []),
        "failed_criteria": consensus.get("failed_criteria", []),
        "summary": _summary_from_verdicts(verdicts, verdict),
        "report_path": str(report_path),
    }
    if consensus.get("reason"):
        result["error_reason"] = consensus["reason"]
    report_path.write_text(render_report(result), encoding="utf-8")
    report_path.with_suffix(report_path.suffix + ".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _summary_from_verdicts(verdicts: dict[str, dict], final_verdict: str) -> str:
    summaries = [str(v.get("summary", "")).strip() for v in verdicts.values() if v.get("summary")]
    if summaries:
        return "; ".join(summaries[:3])
    return f"review-diff completed with verdict={final_verdict}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Review current git diff with external evaluators")
    parser.add_argument("--project-root", default=".")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--mode", choices=sorted(VALID_MODES), default=None)
    mode_group.add_argument("--advisory", action="store_true", help="Shortcut for --mode advisory")
    mode_group.add_argument("--strict", action="store_true", help="Shortcut for --mode strict")
    parser.add_argument("--models", default="", help="Comma-separated model names; defaults to ahoy_config.json")
    parser.add_argument("--min-models", type=int, default=None)
    parser.add_argument("--evaluator-command", default=None, help="Optional shell command for tests/custom evaluator; prompt is stdin")
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else None
    mode = "strict" if args.strict else "advisory" if args.advisory else args.mode or "advisory"
    result = run_review_diff(
        Path(args.project_root),
        mode=mode,
        models=models,
        evaluator_command=args.evaluator_command,
        min_models=args.min_models,
        report_path=Path(args.report),
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] in {"passed", "no_diff"}:
        return 0
    return 2 if result["status"] == "error" else 1


if __name__ == "__main__":
    sys.exit(main())
