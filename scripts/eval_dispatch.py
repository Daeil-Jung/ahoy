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


def parse_acceptance_criteria(contract: str) -> list[dict[str, str]]:
    """Parse acceptance criteria from contract.md.

    Looks for a section headed '## Acceptance Criteria' or '### Acceptance Criteria',
    then extracts list items starting with '- [ ]' or '- '.
    Returns a list of dicts: [{"id": "AC-1", "description": "..."}, ...]
    """
    # Find the AC section (## or ###)
    pattern = re.compile(
        r"^#{2,3}\s+Acceptance\s+Criteria\s*$\n(?P<body>.*?)(?=^#{2,3}\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(contract)
    if not match:
        return []

    criteria: list[dict[str, str]] = []
    idx = 0
    for line in match.group("body").splitlines():
        stripped = line.strip()
        # Skip indented sub-bullets (lines starting with whitespace before - or *)
        if re.match(r"^\s+[-*]\s+", line):
            continue
        # Match '- [ ] ...' or '- [x] ...' or '- ...' (but not sub-items or empty)
        ac_match = re.match(r"^[-*]\s+(?:\[[ x]]\s+)?(.+)$", stripped, re.IGNORECASE)
        if ac_match:
            text = ac_match.group(1).strip()
            # Extract explicit AC ID from the text (e.g., "AC-001: description" or "**AC-001** description")
            id_match = re.match(r"\*{0,2}(AC-\d+)\*{0,2}[:\s\-–—]+(.+)", text, re.IGNORECASE)
            if id_match:
                ac_id = id_match.group(1).upper()
                description = id_match.group(2).strip()
            else:
                idx += 1
                ac_id = f"AC-{idx}"
                description = text
            criteria.append({"id": ac_id, "description": description})

    return criteria


def build_eval_prompt(contract: str, gen_report: str, code_snippets: str) -> str:
    """Build the evaluation prompt using G-Eval 4-step Chain-of-Thought structure.

    Steps:
        1. Code Understanding — analyse structure and behaviour of implemented code
        2. AC Verification — verify each Acceptance Criterion from contract.md
        3. Quality Assessment — code quality, security, performance, maintainability
        4. Final Verdict — synthesise a verdict with reasoning chain
    """
    # Filter Generator's self-assessment from gen_report
    sanitized_report = strip_generator_opinions(gen_report)

    # Parse individual acceptance criteria for per-AC evaluation
    criteria = parse_acceptance_criteria(contract)
    criteria_section = ""
    if criteria:
        criteria_lines = [f"- **{c['id']}**: {c['description']}" for c in criteria]
        criteria_section = (
            "\n\n## Acceptance Criteria (evaluate each individually)\n"
            + "\n".join(criteria_lines)
        )

    criteria_results_schema = ""
    if criteria:
        criteria_results_schema = """
  "criteria_results": [
    {{
      "criterion_id": "AC-1",
      "description": "criterion description",
      "verdict": "pass or fail",
      "evidence": "specific evidence from the code"
    }}
  ],
  "convergence_ratio": 0.75,"""

    return f"""You are an independent code reviewer. Evaluate the Generator's implementation using a structured 4-step Chain-of-Thought process.

## Sprint Contract (this is the evaluation criteria)
{contract}
{criteria_section}

## Generator Report (only file lists and statistics for reference — all Generator opinions have been removed)
{sanitized_report}

## Implemented Code
{code_snippets}

## Review Instructions
1. Strictly evaluate whether each acceptance criterion (AC) is satisfied — judge each AC individually as pass or fail
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
## Evaluation Process — follow these 4 steps IN ORDER

### Step 1 — Code Understanding
Analyse the structure and behaviour of the implemented code. Identify:
- What files were created or modified and their purpose
- Key functions, classes, and data flows
- How the implementation addresses the sprint contract

### Step 2 — AC Verification
For EACH acceptance criterion (AC) in the contract:
- Determine whether it is satisfied, partially satisfied, or not satisfied
- Cite specific code evidence (file, function, line-level details)
- Do not trust claims in the Generator report — read and judge the code directly

### Step 3 — Quality Assessment
Evaluate the code on these dimensions:
- **Correctness**: Does the logic work as intended?
- **Security**: Are there vulnerabilities or unsafe patterns?
- **Performance**: Are there unnecessary inefficiencies?
- **Maintainability**: Is the code readable, well-structured, and documented?

### Step 4 — Final Verdict
Synthesise findings from Steps 1-3 into a final verdict. Do not give lenient verdicts like "this is good enough".

## Response Format
Respond ONLY in the following JSON format (no text outside JSON).
The `reasoning_chain` field is REQUIRED — you must fill every sub-field before deciding the verdict.

```json
{{
  "verdict": "pass or partial_pass or fail",{criteria_results_schema}
  "objections": [
    "at least one concrete concern or improvement suggestion (REQUIRED, minimum 1)"
  ],
  "reasoning_chain": {{
    "code_understanding": "Step 1 summary: structure and behaviour analysis",
    "ac_verification": "Step 2 summary: per-AC pass/fail with code evidence",
    "quality_assessment": "Step 3 summary: correctness, security, performance, maintainability",
    "final_reasoning": "Step 4 summary: why the verdict was chosen based on the above"
  }},
  "issues": [
    {{
      "id": "ISS-001",
      "severity": "blocker or major or minor",
      "category": "functional or test or quality or performance",
      "description": "specific issue description",
      "acceptance_criterion": "AC-001",
      "suggested_fix": "suggested fix direction",
      "suggestion": "concrete fix direction — which file, which section, and how to change it"
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

    If the objections field is missing or empty, log a warning but preserve the
    original verdict.  External LLMs may not reliably produce every requested
    JSON field, so a missing objections list should not cascade into a total
    evaluation failure.
    """
    # If the model already errored (e.g. CLI timeout, JSON parse failure),
    # preserve the original error information — skip objection validation.
    if parsed.get("verdict") == "error":
        return parsed

    raw = parsed.get("objections")
    # Normalise to a list of non-empty strings
    if isinstance(raw, list):
        parsed["objections"] = [o for o in raw if isinstance(o, str) and o.strip()]
    else:
        parsed["objections"] = []

    if not parsed["objections"]:
        print(
            f"[eval_dispatch] WARNING: {model}: objections field missing or empty. "
            "Evaluators should provide at least one concrete concern or improvement.",
            file=sys.stderr,
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


def _error_result(sprint_dir: Path, models: list[str], reason: str) -> dict:
    """Build an error-state result dict for early-abort paths."""
    return {
        "sprint": sprint_dir.name,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "models_used": models,
        "models_valid": [],
        "verdict": "error",
        "model_verdicts": {},
        "issues": [],
        "passed_criteria": [],
        "failed_criteria": [],
        "error_reason": reason,
        "status_action": "error",
    }


def write_result(sprint_dir: Path, result: dict) -> None:
    issues_path = sprint_dir / "issues.json"
    issues_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval_dispatch] Result saved: {issues_path}", file=sys.stderr)


def _merge_criteria_results(
    valid_verdicts: dict[str, dict],
    known_criteria: list[dict[str, str]] | None = None,
) -> tuple[list[dict], float]:
    """Merge per-criterion results across models and compute convergence_ratio.

    A criterion is considered passed only if ALL valid models marked it as pass.
    If a model omits a criterion entirely, it is treated as fail for that model.
    The denominator for convergence_ratio is the total number of valid (non-error)
    models, not just those that reported criteria_results.
    Returns (merged_criteria_results, convergence_ratio).
    If no model provided criteria_results, returns ([], 0.0).
    """
    all_valid_model_names = list(valid_verdicts.keys())

    # Collect criteria_results from each model
    per_model: dict[str, list[dict]] = {}
    for model_name, result in valid_verdicts.items():
        cr = result.get("criteria_results")
        if cr and isinstance(cr, list):
            per_model[model_name] = cr

    if not per_model:
        return [], 0.0

    model_names = all_valid_model_names

    # Build a unified set of criterion IDs, seeded from known_criteria if available
    all_criteria: dict[str, dict] = {}  # id -> merged result

    if known_criteria:
        for kc in known_criteria:
            cid = kc["id"]
            all_criteria[cid] = {
                "criterion_id": cid,
                "description": kc.get("description", ""),
                "verdict": "pass",
                "model_verdicts": {},
                "evidence": [],
            }

    for model_name, cr_list in per_model.items():
        for cr in cr_list:
            cid = cr.get("criterion_id", "")
            if not cid:
                continue
            if cid not in all_criteria:
                all_criteria[cid] = {
                    "criterion_id": cid,
                    "description": cr.get("description", ""),
                    "verdict": "pass",
                    "model_verdicts": {},
                    "evidence": [],
                }
            # A criterion fails consensus if any model says fail
            model_verdict = cr.get("verdict", "fail").lower()
            all_criteria[cid]["model_verdicts"][model_name] = model_verdict
            if model_verdict != "pass":
                all_criteria[cid]["verdict"] = "fail"
            evidence = cr.get("evidence", "")
            if evidence:
                all_criteria[cid]["evidence"].append(f"[{model_name}] {evidence}")

    if not all_criteria:
        return [], 0.0

    # Treat missing criteria as fail: if a model did not report a criterion, mark it as fail
    for cid, entry in all_criteria.items():
        for model_name in model_names:
            if model_name not in entry["model_verdicts"]:
                entry["model_verdicts"][model_name] = "fail"
                entry["verdict"] = "fail"
                entry["evidence"].append(f"[{model_name}] criterion not reported — treated as fail")

    # Build final list sorted by criterion ID (natural order: AC-1, AC-2, ..., AC-10)
    def _ac_sort_key(cid: str) -> tuple[str, int]:
        m = re.match(r"^(.*?)(\d+)$", cid)
        return (m.group(1), int(m.group(2))) if m else (cid, 0)

    merged: list[dict] = []
    for cid in sorted(all_criteria.keys(), key=_ac_sort_key):
        entry = all_criteria[cid]
        merged.append({
            "criterion_id": entry["criterion_id"],
            "description": entry["description"],
            "verdict": entry["verdict"],
            "model_verdicts": entry["model_verdicts"],
            "evidence": "; ".join(entry["evidence"]) if entry["evidence"] else "",
        })

    total = len(merged)
    passed = sum(1 for c in merged if c["verdict"] == "pass")
    ratio = round(passed / total, 4) if total > 0 else 0.0

    return merged, ratio


def compute_consensus(
    verdicts: dict[str, dict],
    min_valid_models: int = 2,
    known_criteria: list[dict[str, str]] | None = None,
) -> dict:
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

    def _build_model_details(src: dict[str, dict]) -> dict[str, dict]:
        details: dict[str, dict] = {}
        for k, v in src.items():
            d: dict = {"verdict": v.get("verdict")}
            if v.get("reasoning_chain"):
                d["reasoning_chain"] = v["reasoning_chain"]
            details[k] = d
        return details

    if not valid:
        return {
            "consensus_verdict": "error",
            "reason": "All external model calls failed",
            "model_verdicts": _build_model_details(verdicts),
        }

    if len(valid) < min_valid_models:
        return {
            "consensus_verdict": "error",
            "reason": f"Valid models {len(valid)} < minimum {min_valid_models} required. "
                      f"Failed models: {', '.join(error_models)}",
            "model_verdicts": _build_model_details(verdicts),
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

    # Merge per-criterion results across models
    criteria_results, convergence_ratio = _merge_criteria_results(valid, known_criteria)

    result = {
        "consensus_verdict": consensus,
        "model_verdicts": _build_model_details(verdicts),
        "issues": all_issues,
        "objections": all_objections,
        "passed_criteria": sorted(all_passed),
        "failed_criteria": sorted(all_failed),
    }

    if criteria_results:
        result["criteria_results"] = criteria_results
        result["convergence_ratio"] = convergence_ratio

    return result


def check_verdict_conflict(verdicts: dict[str, dict]) -> bool:
    """Check if valid model verdicts conflict (hard pass/fail disagreement).

    Returns True only when some models say pass/partial_pass and others say fail.
    Models with verdict 'error' are excluded from the check.
    Soft disagreements (pass vs partial_pass) do not count as conflicts.
    """
    valid = {k: v for k, v in verdicts.items() if v.get("verdict") not in ("error", None)}
    if len(valid) < 2:
        return False
    verdict_values = {v["verdict"] for v in valid.values()}
    # Only conflict if there's a mix of fail and non-fail
    has_fail = "fail" in verdict_values
    has_non_fail = bool(verdict_values - {"fail"})
    return has_fail and has_non_fail


def build_round2_prompt(base_prompt: str, round1_verdicts: dict[str, dict]) -> str:
    """Build a round-2 prompt that includes round-1 verdicts and reasoning.

    Uses the same JSON response schema as round 1.
    """
    round1_summary_parts: list[str] = []
    for model, result in round1_verdicts.items():
        if result.get("verdict") == "error":
            continue
        verdict = result.get("verdict", "unknown")
        summary = result.get("summary", "No summary provided")
        reasoning_issues = result.get("issues", [])
        issues_text = ""
        if reasoning_issues:
            issue_lines = [
                f"  - [{iss.get('severity', '?')}] {iss.get('description', 'N/A')}"
                for iss in reasoning_issues[:10]
            ]
            issues_text = "\n".join(issue_lines)
        round1_summary_parts.append(
            f"### {model}\n- Verdict: {verdict}\n- Summary: {summary}"
            + (f"\n- Issues:\n{issues_text}" if issues_text else "")
        )

    round1_block = "\n\n".join(round1_summary_parts)

    return f"""{base_prompt}

---

## Round 2 — Cross-Verification

The following models provided conflicting assessments in Round 1. Review their reasoning and provide your independent verdict:

{round1_block}

Given the conflicting assessments above, re-examine the code against the contract criteria and provide your own independent verdict. Respond ONLY in the same JSON format specified above."""

_REASONING_CHAIN_KEYS = ("code_understanding", "ac_verification", "quality_assessment", "final_reasoning")


def _warn_if_missing_reasoning_chain(model: str, parsed: dict) -> None:
    """Log a warning if reasoning_chain is absent or incomplete.

    This is a soft check for backward-compatibility — it does NOT set verdict to error.
    """
    chain = parsed.get("reasoning_chain")
    if chain is None:
        print(f"[eval_dispatch] WARNING: {model} response missing reasoning_chain", file=sys.stderr)
        return
    if not isinstance(chain, dict):
        print(f"[eval_dispatch] WARNING: {model} reasoning_chain is not a dict", file=sys.stderr)
        return
    missing = [k for k in _REASONING_CHAIN_KEYS if not chain.get(k)]
    if missing:
        print(
            f"[eval_dispatch] WARNING: {model} reasoning_chain incomplete, missing: {', '.join(missing)}",
            file=sys.stderr,
        )


def load_config() -> dict:
    """Load ahoy_config.json from plugin root if available.

    Applies defaults for cost_limit when not specified (None = unlimited).
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    config: dict = {}
    if plugin_root:
        config_path = Path(plugin_root) / "ahoy_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    # Apply cost_limit defaults — None means unlimited
    config.setdefault("cost_limit", None)
    return config


def parse_usage(response: str, parsed: dict | None = None) -> dict:
    """Extract usage/token information from a model response.

    *parsed* may be supplied when the caller has already extracted JSON from
    *response* (avoids re-parsing).  Falls back to estimating token counts
    from the response length when no explicit usage data is present.
    """
    if parsed is None:
        parsed = extract_json(response)
    if parsed and "usage" in parsed:
        usage = parsed["usage"]
        return {
            "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens", 0)),
            "output_tokens": usage.get("output_tokens", usage.get("completion_tokens", 0)),
        }

    # Fallback: rough estimate based on character length (approx 4 chars per token).
    # This is a best-effort estimate — the eval prompt requests JSON-only responses
    # without a ``usage`` field, so models will almost always reach this path.
    char_count = len(response)
    estimated_output = max(char_count // 4, 0)
    return {"input_tokens": 0, "output_tokens": estimated_output}


def update_cost_tracking(
    harness_state_path: Path,
    eval_calls: int,
    tokens: int,
    sprint_id: str = "",
    attempt: int = 0,
) -> None:
    """Append cost data to the ``cost_tracking`` field in harness_state.json."""
    state: dict = {}
    try:
        state = json.loads(harness_state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass  # First run — start fresh
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[eval_dispatch] WARNING: Failed to read harness_state.json for cost tracking: {exc}", file=sys.stderr)
        return  # Do not write back — would clobber existing data

    tracking = state.setdefault("cost_tracking", {
        "total_eval_calls": 0,
        "total_tokens": 0,
        "history": [],
    })

    tracking["total_eval_calls"] = tracking.get("total_eval_calls", 0) + eval_calls
    tracking["total_tokens"] = tracking.get("total_tokens", 0) + tokens
    tracking.setdefault("history", []).append({
        "sprint_id": sprint_id,
        "attempt": attempt,
        "eval_calls": eval_calls,
        "tokens": tokens,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    harness_state_path.parent.mkdir(parents=True, exist_ok=True)
    harness_state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def check_cost_limit(harness_state_path: Path, config: dict, pending_calls: int = 0) -> bool:
    """Return True if accumulated costs exceed the configured limit (abort).

    When *pending_calls* > 0 the check also verifies that the totals **after**
    this run would still be within limits, preventing an overshoot that would
    only be caught on the next invocation.

    Returns False (no abort) when ``cost_limit`` is ``None`` or absent.
    """
    cost_limit = config.get("cost_limit")
    if not cost_limit:
        return False

    try:
        state = json.loads(harness_state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return False

    tracking = state.get("cost_tracking", {})
    total_calls = tracking.get("total_eval_calls", 0)
    total_tokens = tracking.get("total_tokens", 0)

    max_calls = cost_limit.get("max_eval_calls")
    max_tokens = cost_limit.get("max_tokens")

    if max_calls is not None and total_calls + pending_calls > max_calls:
        return True
    if max_tokens is not None and total_tokens >= max_tokens:
        return True

    return False


def _record_convergence(
    sprint_dir: Path, project_root: Path, convergence_ratio: float,
) -> None:
    """Append convergence_ratio to the current sprint's convergence_history in harness_state.json.

    This enables tracking of convergence trends across rework attempts.
    """
    harness_path = project_root / ".claude" / "harness" / "harness_state.json"
    if not harness_path.exists():
        return

    try:
        state = json.loads(harness_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    sprint_name = sprint_dir.name
    sprints = state.get("sprints", [])

    for sprint in sprints:
        if sprint.get("sprint_id") == sprint_name:
            history = sprint.setdefault("convergence_history", [])
            attempt = sprint.get("attempt", len(history))
            history.append({
                "attempt": attempt,
                "convergence_ratio": convergence_ratio,
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
            })
            break
    else:
        # Sprint not found — skip silently
        return

    try:
        # Subprocess write — bypasses hook enforcement by design (same as write_result for issues.json)
        harness_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(
            f"[eval_dispatch] Convergence {convergence_ratio} recorded for {sprint_name}",
            file=sys.stderr,
        )
    except OSError as exc:
        print(f"[eval_dispatch] Failed to update harness_state.json: {exc}", file=sys.stderr)


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

    # Resolve harness_state.json path for cost tracking
    harness_state_path = project_root / ".claude" / "harness" / "harness_state.json"

    # Check cost limit before proceeding (include pending calls for this run)
    if check_cost_limit(harness_state_path, config, pending_calls=len(models)):
        cost_limit = config.get("cost_limit", {})
        print(
            f"ABORT: Cost limit exceeded. "
            f"max_eval_calls={cost_limit.get('max_eval_calls')}, "
            f"max_tokens={cost_limit.get('max_tokens')}. "
            f"Review cost_tracking in harness_state.json or increase limits in ahoy_config.json.",
            file=sys.stderr,
        )
        result = _error_result(sprint_dir, models, "Cost limit exceeded")
        write_result(sprint_dir, result)
        return 1

    # Read inputs
    contract_path = sprint_dir / "contract.md"
    if not contract_path.exists():
        print(f"ERROR: {contract_path} not found", file=sys.stderr)
        result = _error_result(sprint_dir, models, "contract.md not found")
        write_result(sprint_dir, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    contract = contract_path.read_text(encoding="utf-8")

    gen_report = ""
    gen_report_path = sprint_dir / "gen_report.md"
    if gen_report_path.exists():
        gen_report = gen_report_path.read_text(encoding="utf-8")

    try:
        code_snippets = collect_code_snippets(sprint_dir, project_root)
    except ValueError as exc:
        result = _error_result(sprint_dir, models, str(exc))
        write_result(sprint_dir, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    # Evaluation prompt
    prompt = build_eval_prompt(contract, gen_report, code_snippets)

    # Call each model in parallel
    print(f"[eval_dispatch] Evaluation models: {models} (parallel calls)", file=sys.stderr)
    verdicts: dict[str, dict] = {}

    raw_responses: dict[str, str] = {}

    def _call_and_parse(model: str, eval_prompt: str) -> tuple[str, dict, str]:
        """Call a single model and parse JSON response.  Returns (model, parsed, raw)."""
        print(f"[eval_dispatch] Calling {model}...", file=sys.stderr)
        raw = call_model(model, eval_prompt, timeout=args.timeout)
        parsed = extract_json(raw)
        if parsed:
            parsed = validate_objections(parsed, model)
            print(f"[eval_dispatch] {model} verdict: {parsed.get('verdict')}", file=sys.stderr)
            _warn_if_missing_reasoning_chain(model, parsed)
            return model, parsed, raw
        print(f"[eval_dispatch] {model} raw output (first 500): {raw[:500]}", file=sys.stderr)
        print(f"[eval_dispatch] {model} parsing failed", file=sys.stderr)
        return model, {
            "verdict": "error",
            "error": f"JSON parsing failed. Raw: {raw[:300]}",
            "issues": [],
            "passed_criteria": [],
            "failed_criteria": [],
            "summary": "Response parsing failed",
        }, raw

    # --- Round 1 ---
    print("[eval_dispatch] Round 1: initial evaluation", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {executor.submit(_call_and_parse, m, prompt): m for m in models}
        for future in concurrent.futures.as_completed(futures):
            model_name, result, raw = future.result()
            verdicts[model_name] = result
            raw_responses[model_name] = raw

    # --- Cost tracking helper ---
    def _calc_round_tokens(
        raw_responses: dict[str, str],
        verdicts: dict[str, dict],
        prompt_len: int,
    ) -> int:
        """Calculate total token usage for a single evaluation round."""
        tokens = 0
        estimate = prompt_len // 4
        for model_name, raw in raw_responses.items():
            parsed_verdict = verdicts.get(model_name, {})
            is_local_error = (
                parsed_verdict.get("verdict") == "error"
                and "call failed" in parsed_verdict.get("summary", "")
            )
            if is_local_error:
                continue
            usage = parse_usage(raw, parsed=parsed_verdict)
            tokens += usage["output_tokens"]
            if usage["input_tokens"] > 0:
                tokens += usage["input_tokens"]
            else:
                tokens += estimate
        return tokens

    round1_tokens = _calc_round_tokens(raw_responses, verdicts, len(prompt))

    # Read the current sprint's attempt number from harness_state.json
    current_attempt = 0
    try:
        hs = json.loads(harness_state_path.read_text(encoding="utf-8"))
        for sp in hs.get("sprints", []):
            if sp.get("sprint_id") == sprint_dir.name:
                current_attempt = sp.get("attempt", 0)
                break
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        pass

    round1_verdicts = dict(verdicts)
    evaluation_rounds = 1
    round2_verdicts: dict[str, dict] | None = None
    round2_tokens = 0

    # --- Round 2 (only if verdicts conflict) ---
    if check_verdict_conflict(verdicts):
        evaluation_rounds = 2
        print("[eval_dispatch] Round 1 verdicts conflict — starting Round 2 cross-verification", file=sys.stderr)
        round2_prompt = build_round2_prompt(prompt, round1_verdicts)
        round2_verdicts = {}
        round2_raw: dict[str, str] = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
            futures = {executor.submit(_call_and_parse, m, round2_prompt): m for m in models}
            for future in concurrent.futures.as_completed(futures):
                model_name, result, _raw = future.result()
                round2_verdicts[model_name] = result
                round2_raw[model_name] = _raw

        round2_tokens = _calc_round_tokens(round2_raw, round2_verdicts, len(round2_prompt))

        # Use round 2 verdicts only if quorum is maintained
        round2_valid = {k: v for k, v in round2_verdicts.items() if v.get("verdict") != "error"}
        if len(round2_valid) >= args.min_models:
            verdicts = round2_verdicts
        else:
            print(f"[eval_dispatch] Round 2 quorum lost ({len(round2_valid)} valid < {args.min_models} required), using round 1 results", file=sys.stderr)
    else:
        print("[eval_dispatch] Round 1 unanimous — skipping Round 2", file=sys.stderr)

    # Persist cost tracking for all rounds
    total_eval_calls = len(models) * evaluation_rounds
    total_tokens_this_run = round1_tokens + round2_tokens
    update_cost_tracking(
        harness_state_path,
        eval_calls=total_eval_calls,
        tokens=total_tokens_this_run,
        sprint_id=sprint_dir.name,
        attempt=current_attempt,
    )

    # Compute consensus (pass known criteria from contract for missing-criterion detection)
    known_criteria = parse_acceptance_criteria(contract)
    consensus = compute_consensus(verdicts, min_valid_models=args.min_models, known_criteria=known_criteria)

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
        "evaluation_rounds": evaluation_rounds,
        "round1_verdicts": {k: v.get("verdict") for k, v in round1_verdicts.items()},
    }

    # Include per-criterion results and convergence ratio if available
    if consensus.get("criteria_results"):
        result["criteria_results"] = consensus["criteria_results"]
        result["convergence_ratio"] = consensus["convergence_ratio"]

    if round2_verdicts is not None:
        result["round2_verdicts"] = {k: v.get("verdict") for k, v in round2_verdicts.items()}
    result["status_action"] = derive_status_action(result["verdict"], result["issues"])

    # Aggregate reasoning_chain from consensus model_verdicts (already computed)
    reasoning_chains = {
        name: detail["reasoning_chain"]
        for name, detail in consensus.get("model_verdicts", {}).items()
        if detail.get("reasoning_chain")
    }
    if reasoning_chains:
        result["reasoning_chain"] = reasoning_chains

    # Include reason if error
    if consensus.get("reason"):
        result["error_reason"] = consensus["reason"]

    # Save issues.json
    write_result(sprint_dir, result)

    # Record convergence in harness_state.json for trend tracking
    if "convergence_ratio" in result:
        _record_convergence(sprint_dir, project_root, result["convergence_ratio"])

    # Also output to stdout (so Claude can read it)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status_action"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
