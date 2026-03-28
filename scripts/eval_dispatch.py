#!/usr/bin/env python3
"""External model evaluation dispatcher.

Calls external models in a process completely separated from Claude (Generator) to evaluate code.
Claude can only read the output (issues.json) of this script and cannot change the verdict.

Usage:
    python eval_dispatch.py <sprint_dir> [--models codex,gemini] [--project-root .]

Supported models:
    codex   - OpenAI Codex CLI (codex exec --yolo --ephemeral)
    gemini  - Google Gemini CLI (gemini -p)
    claude  - Anthropic Claude CLI (claude -p) — separate process, so context is isolated from Generator
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Detect Windows environment
_IS_WINDOWS = sys.platform == "win32"


def strip_generator_opinions(gen_report: str) -> str:
    """Remove Generator's self-assessment/opinions from gen_report.md, keeping only factual information.

    Kept: file lists, line counts, test execution commands/results
    Removed: "satisfied", "pass", "completed", subjective judgments
    """
    if not gen_report.strip():
        return gen_report

    filtered_lines = []
    opinion_patterns = re.compile(
        r"(satisfied|pass|passed|completed|no\s*issues|successful|works\s*well|works\s*correctly)",
        re.IGNORECASE,
    )

    for line in gen_report.split("\n"):
        # Remove judgment column values from "acceptance criteria mapping" section tables
        # But keep factual information like file lists, line counts, etc.
        stripped = line.strip()

        if stripped.startswith("#"):
            filtered_lines.append(line)
            continue

        # Always keep file lists (- path/to/file)
        if re.match(r"^[-*]\s+`?[^\s`]+\.\w+", stripped):
            filtered_lines.append(line)
            continue

        # Keep numeric/statistics info ("+N / -M lines", etc.)
        if re.search(r"[+\-]\d+\s*/\s*[+\-]?\d+", stripped):
            filtered_lines.append(line)
            continue

        # Keep test execution results (N passed, M failed)
        if re.search(r"\d+\s*(passed|failed|error)", stripped, re.IGNORECASE):
            filtered_lines.append(line)
            continue

        # Keep table separator lines
        if re.match(r"^\|[-\s|:]+\|$", stripped):
            filtered_lines.append(line)
            continue

        # Keep numeric test results with units (e.g., "12 passed", "3 completed") as factual info
        if re.search(r"\d+\s*(tests?|cases?|items?)\s*(passed|completed|succeeded|failed)", stripped, re.IGNORECASE):
            filtered_lines.append(line)
            continue

        # Replace lines containing Generator's subjective opinions with "[Generator opinion removed]"
        if opinion_patterns.search(stripped) and not stripped.startswith("|"):
            filtered_lines.append("[Generator opinion removed — verify the code directly]")
            continue

        filtered_lines.append(line)

    return "\n".join(filtered_lines)


def build_eval_prompt(contract: str, gen_report: str, code_snippets: str) -> str:
    """Build the evaluation prompt."""
    # Filter Generator's self-assessment from gen_report
    sanitized_report = strip_generator_opinions(gen_report)

    return f"""You are an independent code reviewer. Verify whether the Generator implemented the code correctly according to the sprint contract.

## Sprint Contract (this is the evaluation criteria)
{contract}

## Generator Report (only file lists and statistics for reference — all Generator opinions have been removed)
{sanitized_report}

## Implemented Code
{code_snippets}

## Review Instructions
1. Strictly evaluate whether each acceptance criterion (AC) is satisfied
2. Identify issues from code quality, security, and performance perspectives
3. Do not give lenient verdicts like "this is good enough"
4. Do not trust claims in the Generator report — read and judge the code directly

## Forced Objection
- List at least one concern or improvement, even if minor.
- Even if the implementation looks correct, you MUST provide at least one concrete suggestion for improvement (e.g., edge cases, naming, documentation, test coverage, error handling).
- If you cannot find any issue, suggest a minor improvement anyway — no review is complete without at least one actionable objection.

## Active Rejection
- Do NOT default to PASS — justify your verdict with specific evidence.
- A "pass" verdict requires explicit justification for why each acceptance criterion is met.
- If in doubt, lean toward "partial_pass" or "fail" rather than "pass".

5. Respond ONLY in the following JSON format (no text outside JSON):

```json
{{
  "verdict": "pass or partial_pass or fail",
  "objections": [
    "at least one concrete concern or improvement suggestion (REQUIRED, minimum 1)"
  ],
  "issues": [
    {{
      "id": "ISS-001",
      "severity": "blocker or major or minor",
      "category": "functional or test or quality or performance",
      "description": "specific issue description",
      "acceptance_criterion": "AC-001",
      "suggested_fix": "suggested fix direction"
    }}
  ],
  "passed_criteria": ["AC-001"],
  "failed_criteria": ["AC-002"],
  "summary": "one-line overall evaluation summary"
}}
```"""


def _build_cmd_string(cmd: list[str]) -> str:
    """Convert a command list to a string safe for shell=True.

    On Windows, using shell=True + list can cause arguments to be dropped,
    so we explicitly convert to a string.
    """
    if _IS_WINDOWS:
        # Windows: use subprocess.list2cmdline (shlex.join is POSIX only)
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def call_model(model: str, prompt: str, timeout: int = 600) -> str:
    """Call an external model CLI using stdin for the prompt."""
    output_file: str | None = None

    try:

        if model == "codex":
            # codex exec: --dangerously-bypass-approvals-and-sandbox (auto-approve),
            # --ephemeral (no session saved), -o/--output-last-message: save final response to file
            # - : read prompt from stdin
            output_file = str(Path.cwd() / f".ahoy-codex-output-{os.getpid()}.txt")
            cmd = [
                "codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--ephemeral",
                "--output-last-message", output_file, "-",
            ]
            stdin_data = prompt
        elif model == "gemini":
            # gemini: -p/--prompt (non-interactive headless mode)
            # Use a short -p flag with stdin carrying the actual prompt content
            # (gemini docs: "Appended to input on stdin if any")
            cmd = ["gemini", "--prompt", "Evaluate the code as instructed below via stdin."]
            stdin_data = prompt
        elif model == "claude":
            # claude: -p (non-interactive), pipe prompt via stdin
            # --output-format text: text output (json also available)
            cmd = ["claude", "-p", "--output-format", "text"]
            stdin_data = prompt
        else:
            raise ValueError(f"Unsupported model: {model}. Available: codex, gemini, claude")

        cmd_str = _build_cmd_string(cmd)

        result = subprocess.run(
            cmd_str,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            shell=True,
        )

        print(f"[eval_dispatch] {model} exit code: {result.returncode}", file=sys.stderr)

        # codex: read from --output-file (most reliable)
        if output_file and Path(output_file).exists():
            output = Path(output_file).read_text(encoding="utf-8")
            Path(output_file).unlink(missing_ok=True)
            if output.strip():
                return output

        if result.returncode != 0 and not result.stdout.strip():
            print(f"[eval_dispatch] {model} stderr: {result.stderr[:500]}", file=sys.stderr)
            return _error_json(model, f"CLI execution failed (exit {result.returncode}): {result.stderr[:300]}")

        return result.stdout

    except FileNotFoundError:
        return _error_json(model, f"{model} CLI not found.")
    except subprocess.TimeoutExpired:
        return _error_json(model, f"Response timeout ({timeout}s)")
    except Exception as e:
        print(f"[eval_dispatch] {model} exception: {type(e).__name__}: {e}", file=sys.stderr)
        return _error_json(model, f"Exception occurred: {type(e).__name__}: {str(e)[:300]}")
    finally:
        if output_file:
            Path(output_file).unlink(missing_ok=True)


def _error_json(model: str, error: str) -> str:
    return json.dumps({
        "verdict": "error",
        "error": error,
        "issues": [],
        "passed_criteria": [],
        "failed_criteria": [],
        "summary": f"{model} call failed",
    })


def validate_objections(parsed: dict, model: str) -> dict:
    """Validate that the parsed response contains required objections.

    If the objections field is missing or empty, override verdict to 'error'.
    """
    raw = parsed.get("objections")
    # Normalise to a list of non-empty strings
    if isinstance(raw, list):
        parsed["objections"] = [o for o in raw if isinstance(o, str) and o.strip()]
    else:
        parsed["objections"] = []

    if not parsed["objections"]:
        parsed["verdict"] = "error"
        parsed["error"] = (
            f"{model}: objections field missing or empty. "
            "All evaluators must provide at least one concrete concern or improvement."
        )
    return parsed


def extract_json(text: str) -> dict | None:
    """Extract JSON from model response."""
    # Try ```json ... ``` block first
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try extracting { ... } from full text (non-greedy: shortest valid JSON)
    # Use greedy match to handle nested braces, then validate with json.loads
    # On failure, shrink from the end and retry
    brace_start = text.find("{")
    if brace_start == -1:
        return None

    # Search for valid JSON by finding } from the end
    brace_end = text.rfind("}")
    while brace_end >= brace_start:
        candidate = text[brace_start:brace_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            brace_end = text.rfind("}", brace_start, brace_end)

    return None


def _extract_inventory_section(content: str, heading: str) -> list[str]:
    pattern = re.compile(
        rf"^###\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^###\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        return []

    files: list[str] = []
    for line in match.group("body").splitlines():
        stripped = line.strip()
        file_match = re.match(r"^[-*]\s+`?([^`\s]+\.\w+)`?$", stripped)
        if file_match:
            files.append(file_match.group(1))
    return files


def resolve_reported_files(gen_report: str) -> list[str]:
    """Resolve the generator's structured file inventory from gen_report.md."""
    files = _extract_inventory_section(gen_report, "Files Created")
    files.extend(_extract_inventory_section(gen_report, "Files Modified"))

    if files:
        return list(dict.fromkeys(files))

    # Backward-compatible fallback for older reports.
    fallback_pattern = re.compile(r"^[-*]\s+`?([^\s`]+\.\w+)`?", re.MULTILINE)
    return list(dict.fromkeys(fallback_pattern.findall(gen_report)))


def collect_code_snippets(sprint_dir: Path, project_root: Path) -> str:
    """Read file list from gen_report.md and collect code snippets."""
    gen_report_path = sprint_dir / "gen_report.md"
    if not gen_report_path.exists():
        raise ValueError("gen_report.md not found")

    content = gen_report_path.read_text(encoding="utf-8")
    snippets = []
    files = resolve_reported_files(content)

    if not files:
        raise ValueError(
            "No code files were declared in gen_report.md. "
            "Generator reports must include structured '### Files Created'/'### Files Modified' sections.",
        )

    for file_rel in files[:20]:  # max 20 files
        file_path = project_root / file_rel
        if file_path.exists() and file_path.stat().st_size < 50_000:
            try:
                code = file_path.read_text(encoding="utf-8")
                snippets.append(f"### {file_rel}\n```\n{code}\n```")
            except (UnicodeDecodeError, OSError):
                pass

    if not snippets:
        raise ValueError("No readable code files from gen_report.md were found under the project root.")

    return "\n\n".join(snippets)


def has_blocker_or_major(issues: list[dict]) -> bool:
    return any(issue.get("severity") in {"blocker", "major"} for issue in issues)


def derive_status_action(verdict: str, issues: list[dict]) -> str:
    if verdict == "pass":
        return "passed"
    if verdict == "partial_pass":
        return "failed" if has_blocker_or_major(issues) else "passed"
    if verdict == "fail":
        return "failed"
    return "error"


def write_result(sprint_dir: Path, result: dict) -> None:
    issues_path = sprint_dir / "issues.json"
    issues_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval_dispatch] Result saved: {issues_path}", file=sys.stderr)


def compute_consensus(verdicts: dict[str, dict], min_valid_models: int = 2) -> dict:
    """Compute consensus from multiple model verdicts.

    Rules:
    - Any error -> exclude that model
    - Valid models fewer than min_valid_models -> error (prevent single-model pass)
    - Any fail -> final fail
    - Any partial_pass -> final partial_pass
    - All pass -> final pass
    """
    valid = {k: v for k, v in verdicts.items() if v.get("verdict") != "error"}
    error_models = [k for k, v in verdicts.items() if v.get("verdict") == "error"]

    if not valid:
        return {
            "consensus_verdict": "error",
            "reason": "All external model calls failed",
            "model_verdicts": {k: v.get("verdict") for k, v in verdicts.items()},
        }

    if len(valid) < min_valid_models:
        return {
            "consensus_verdict": "error",
            "reason": f"Valid models {len(valid)} < minimum {min_valid_models} required. "
                      f"Failed models: {', '.join(error_models)}",
            "model_verdicts": {k: v.get("verdict") for k, v in verdicts.items()},
        }

    verdict_values = [v["verdict"] for v in valid.values()]

    if "fail" in verdict_values:
        consensus = "fail"
    elif "partial_pass" in verdict_values:
        consensus = "partial_pass"
    else:
        consensus = "pass"

    # Merge all issues (no dedup — they may be issues from different perspectives)
    all_issues = []
    for model_name, result in valid.items():
        for issue in result.get("issues", []):
            issue["found_by"] = model_name
            all_issues.append(issue)

    # Merge objections from all valid models
    all_objections: dict[str, list[str]] = {}
    for model_name, result in valid.items():
        model_objections = result.get("objections", [])
        if model_objections:
            all_objections[model_name] = model_objections

    # Merge failed criteria
    all_failed = set()
    all_passed = set()
    for result in valid.values():
        all_failed.update(result.get("failed_criteria", []))
        all_passed.update(result.get("passed_criteria", []))
    # If any model failed a criterion, remove it from passed
    all_passed -= all_failed

    return {
        "consensus_verdict": consensus,
        "model_verdicts": {k: v.get("verdict") for k, v in verdicts.items()},
        "issues": all_issues,
        "objections": all_objections,
        "passed_criteria": sorted(all_passed),
        "failed_criteria": sorted(all_failed),
    }


def load_config() -> dict:
    """Load ahoy_config.json from plugin root if available."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        config_path = Path(plugin_root) / "ahoy_config.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def main() -> int:
    config = load_config()
    default_models = ",".join(config.get("eval_models", ["codex", "claude"]))
    default_min = config.get("min_models", 2)

    parser = argparse.ArgumentParser(description="External model code evaluation dispatcher")
    parser.add_argument("sprint_dir", help="Sprint directory path (.claude/harness/sprints/sprint-NNN)")
    parser.add_argument("--models", default=default_models, help="Models to use (comma-separated: codex,claude,gemini)")
    parser.add_argument("--project-root", default=".", help="Project root path")
    parser.add_argument("--timeout", type=int, default=600, help="Model call timeout (seconds)")
    parser.add_argument("--min-models", type=int, default=default_min, help="Minimum valid model count (default 2)")
    args = parser.parse_args()

    sprint_dir = Path(args.sprint_dir)
    project_root = Path(args.project_root)
    models = [m.strip() for m in args.models.split(",")]

    # Read inputs
    contract_path = sprint_dir / "contract.md"
    if not contract_path.exists():
        print(f"ERROR: {contract_path} not found", file=sys.stderr)
        return 1

    contract = contract_path.read_text(encoding="utf-8")

    gen_report = ""
    gen_report_path = sprint_dir / "gen_report.md"
    if gen_report_path.exists():
        gen_report = gen_report_path.read_text(encoding="utf-8")

    try:
        code_snippets = collect_code_snippets(sprint_dir, project_root)
    except ValueError as exc:
        result = {
            "sprint": sprint_dir.name,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "models_used": models,
            "models_valid": [],
            "verdict": "error",
            "model_verdicts": {},
            "issues": [],
            "passed_criteria": [],
            "failed_criteria": [],
            "error_reason": str(exc),
            "status_action": "error",
        }
        write_result(sprint_dir, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    # Evaluation prompt
    prompt = build_eval_prompt(contract, gen_report, code_snippets)

    # Call each model in parallel
    print(f"[eval_dispatch] Evaluation models: {models} (parallel calls)", file=sys.stderr)
    verdicts: dict[str, dict] = {}

    def _call_and_parse(model: str) -> tuple[str, dict]:
        """Call a single model and parse JSON response."""
        print(f"[eval_dispatch] Calling {model}...", file=sys.stderr)
        raw = call_model(model, prompt, timeout=args.timeout)
        parsed = extract_json(raw)
        if parsed:
            parsed = validate_objections(parsed, model)
            print(f"[eval_dispatch] {model} verdict: {parsed.get('verdict')}", file=sys.stderr)
            return model, parsed
        print(f"[eval_dispatch] {model} raw output (first 500): {raw[:500]}", file=sys.stderr)
        print(f"[eval_dispatch] {model} parsing failed", file=sys.stderr)
        return model, {
            "verdict": "error",
            "error": f"JSON parsing failed. Raw: {raw[:300]}",
            "issues": [],
            "passed_criteria": [],
            "failed_criteria": [],
            "summary": "Response parsing failed",
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {executor.submit(_call_and_parse, m): m for m in models}
        for future in concurrent.futures.as_completed(futures):
            model_name, result = future.result()
            verdicts[model_name] = result

    # Compute consensus
    consensus = compute_consensus(verdicts, min_valid_models=args.min_models)

    # Build result JSON
    result = {
        "sprint": sprint_dir.name,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "models_used": models,
        "models_valid": [k for k, v in verdicts.items() if v.get("verdict") != "error"],
        "verdict": consensus["consensus_verdict"],
        "model_verdicts": consensus.get("model_verdicts", {}),
        "issues": consensus.get("issues", []),
        "objections": consensus.get("objections", {}),
        "passed_criteria": consensus.get("passed_criteria", []),
        "failed_criteria": consensus.get("failed_criteria", []),
    }
    result["status_action"] = derive_status_action(result["verdict"], result["issues"])

    # Include reason if error
    if consensus.get("reason"):
        result["error_reason"] = consensus["reason"]

    # Save issues.json
    write_result(sprint_dir, result)

    # Also output to stdout (so Claude can read it)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status_action"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
