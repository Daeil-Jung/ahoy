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
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Detect Windows environment
_IS_WINDOWS = sys.platform == "win32"

PERSPECTIVES: dict[str, dict[str, str]] = {
    "accuracy_coverage": {
        "name": "Accuracy & Test Coverage",
        "focus": (
            "## Evaluation Perspective: Accuracy & Test Coverage\n\n"
            "Focus your evaluation on:\n"
            "- **Correctness**: Does each function produce the expected output for all inputs?\n"
            "- **Test Coverage**: Are all code paths exercised? Are edge cases tested?\n"
            "- **AC Satisfaction**: Is each acceptance criterion fully met with evidence?\n\n"
            "Give secondary attention to code style and documentation.\n"
        ),
    },
    "security_edge": {
        "name": "Security & Edge Cases",
        "focus": (
            "## Evaluation Perspective: Security & Edge Cases\n\n"
            "Focus your evaluation on:\n"
            "- **Security**: Input validation, injection risks, auth/authz, secret handling\n"
            "- **Edge Cases**: Boundary values, empty inputs, concurrent access, error paths\n"
            "- **Robustness**: How does the code behave under unexpected conditions?\n\n"
            "Give secondary attention to feature completeness.\n"
        ),
    },
}

_SEVERITY_TO_PRIORITY = {
    "blocker": "P0",
    "critical": "P1",
    "major": "P2",
    "minor": "P3",
}

_PRIORITY_TO_SEVERITY = {v: k for k, v in _SEVERITY_TO_PRIORITY.items()}


def normalize_issue_priority(issue: dict) -> dict:
    """Ensure each issue has both severity and priority fields."""
    if "priority" not in issue and "severity" in issue:
        issue["priority"] = _SEVERITY_TO_PRIORITY.get(issue["severity"], "P2")
    elif "severity" not in issue and "priority" in issue:
        issue["severity"] = _PRIORITY_TO_SEVERITY.get(issue["priority"], "major")
    elif "priority" not in issue and "severity" not in issue:
        issue["priority"] = "P2"
        issue["severity"] = "major"
    return issue


_SENSITIVE_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("API_KEY", "MASKED_API_KEY", re.compile(
        r"""(?:api[_-]?key|apikey|api[_-]?token|access[_-]?token|auth[_-]?token)"""
        r"""[\s]*[=:]\s*["']([A-Za-z0-9\-_\.]{20,})["']""",
        re.IGNORECASE,
    )),
    ("PASSWORD", "MASKED_PASSWORD", re.compile(
        r"""(?:password|passwd|pwd|secret)[\s]*[=:]\s*["']([^"'\s]{4,})["']""",
        re.IGNORECASE,
    )),
    ("CONNECTION_STRING", "MASKED_CONN_STRING", re.compile(
        r"""(?:mongodb|postgres|mysql|redis|amqp|sqlite):\/\/[^\s"']+""",
        re.IGNORECASE,
    )),
    ("BEARER_TOKEN", "MASKED_BEARER", re.compile(
        r"""Bearer\s+[A-Za-z0-9\-_\.]{20,}""",
        re.IGNORECASE,
    )),
    ("AWS_KEY", "MASKED_AWS_KEY", re.compile(
        r"""(?:AKIA|ASIA)[A-Z0-9]{16}""",
    )),
    ("PRIVATE_KEY", "MASKED_PRIVATE_KEY", re.compile(
        r"""-----BEGIN[A-Z\s]*PRIVATE\s+KEY-----[\s\S]*?-----END[A-Z\s]*PRIVATE\s+KEY-----""",
    )),
    ("GENERIC_SECRET", "MASKED_SECRET", re.compile(
        r"""(?:secret|credential|token)[\s]*[=:]\s*["']([A-Za-z0-9\-_\.]{16,})["']""",
        re.IGNORECASE,
    )),
]


class SensitiveDataMasker:
    """Detects and masks sensitive data in code strings."""

    def __init__(self, extra_patterns: list[dict] | None = None):
        self._counter: dict[str, int] = {}
        self._mask_map: dict[str, str] = {}
        self._reverse_map: dict[str, str] = {}
        self._patterns = list(_SENSITIVE_PATTERNS)
        if extra_patterns:
            for ep in extra_patterns:
                try:
                    if not isinstance(ep, dict):
                        continue
                    self._patterns.append((
                        ep["category"], ep["mask_prefix"],
                        re.compile(ep["regex"], re.IGNORECASE),
                    ))
                except (KeyError, re.error, TypeError):
                    pass

    def mask(self, text: str) -> str:
        """Replace sensitive data with [MASKED_*] tokens."""
        replacements: list[tuple[int, int, str]] = []

        for _category, prefix, pattern in self._patterns:
            for match in pattern.finditer(text):
                if match.lastindex and match.lastindex >= 1:
                    original = match.group(1)
                    start, end = match.start(1), match.end(1)
                else:
                    original = match.group(0)
                    start, end = match.start(0), match.end(0)

                existing_token = self._reverse_map.get(original)
                if existing_token:
                    token = existing_token
                else:
                    idx = self._counter.get(prefix, 1)
                    self._counter[prefix] = idx + 1
                    token = f"[{prefix}_{idx}]"
                    self._mask_map[token] = original
                    self._reverse_map[original] = token

                replacements.append((start, end, token))

        replacements.sort(key=lambda r: r[0], reverse=True)
        result = text
        for start, end, token in replacements:
            result = result[:start] + token + result[end:]
        return result

    def get_mask_report(self) -> list[dict]:
        return [
            {"token": token, "category": token.rsplit("_", 1)[0].strip("[]")}
            for token in self._mask_map
        ]

    @property
    def masked_count(self) -> int:
        return len(self._mask_map)


def strip_generator_opinions(gen_report: str) -> str:
    """Remove Generator's self-assessment from gen_report.md, keeping only facts."""
    if not gen_report.strip():
        return gen_report

    filtered_lines = []
    opinion_patterns = re.compile(
        r"(satisfied|pass|passed|completed|no\s*issues|successful|works\s*well|works\s*correctly)",
        re.IGNORECASE,
    )

    for line in gen_report.split("\n"):
        stripped = line.strip()

        if stripped.startswith("#"):
            filtered_lines.append(line)
            continue
        if re.match(r"^[-*]\s+`?[^\s`]+\.\w+", stripped):
            filtered_lines.append(line)
            continue
        if re.search(r"[+\-]\d+\s*/\s*[+\-]?\d+", stripped):
            filtered_lines.append(line)
            continue
        if re.search(r"\d+\s*(passed|failed|error)", stripped, re.IGNORECASE):
            filtered_lines.append(line)
            continue
        if re.match(r"^\|[-\s|:]+\|$", stripped):
            filtered_lines.append(line)
            continue
        if re.search(r"\d+\s*(tests?|cases?|items?)\s*(passed|completed|succeeded|failed)", stripped, re.IGNORECASE):
            filtered_lines.append(line)
            continue
        if opinion_patterns.search(stripped) and not stripped.startswith("|"):
            filtered_lines.append("[Generator opinion removed — verify the code directly]")
            continue
        filtered_lines.append(line)

    return "\n".join(filtered_lines)


def parse_acceptance_criteria(contract: str) -> list[dict[str, str]]:
    """Parse acceptance criteria from contract.md."""
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
        if re.match(r"^\s+[-*]\s+", line):
            continue
        ac_match = re.match(r"^[-*]\s+(?:\[[ x]]\s+)?(.+)$", stripped, re.IGNORECASE)
        if ac_match:
            text = ac_match.group(1).strip()
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


def build_eval_prompt(contract: str, gen_report: str, code_snippets: str, perspective: str | None = None) -> str:
    """Build the evaluation prompt using G-Eval 4-step Chain-of-Thought structure."""
    sanitized_report = strip_generator_opinions(gen_report)

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

    perspective_text = ""
    if perspective and perspective in PERSPECTIVES:
        perspective_text = "\n" + PERSPECTIVES[perspective]["focus"]

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
{perspective_text}
## Forced Objection
- List at least one concern or improvement, even if minor.

## Active Rejection
- Do NOT default to PASS — justify your verdict with specific evidence.
- If in doubt, lean toward "partial_pass" or "fail" rather than "pass".

## Evaluation Process — follow these 4 steps IN ORDER

### Step 1 — Code Understanding
Analyse the structure and behaviour of the implemented code.

### Step 2 — AC Verification
For EACH acceptance criterion, determine pass/fail with code evidence.

### Step 3 — Quality Assessment
Evaluate correctness, security, performance, maintainability.

### Step 4 — Final Verdict
Synthesise findings into a final verdict.

## Response Format
Respond ONLY in the following JSON format (no text outside JSON).

```json
{{
  "verdict": "pass or partial_pass or fail",{criteria_results_schema}
  "objections": [
    "at least one concrete concern or improvement suggestion (REQUIRED, minimum 1)"
  ],
  "reasoning_chain": {{
    "code_understanding": "Step 1 summary",
    "ac_verification": "Step 2 summary",
    "quality_assessment": "Step 3 summary",
    "final_reasoning": "Step 4 summary"
  }},
  "issues": [
    {{
      "id": "ISS-001",
      "severity": "blocker or major or minor",
      "priority": "P0 or P1 or P2 or P3",
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
```

Priority Guide:
- P0 (blocker): Prevents core functionality. Must fix immediately.
- P1 (critical): Serious bug or security issue. Must fix in this cycle.
- P2 (major): Significant quality/correctness issue. Should fix.
- P3 (minor): Nit, style, minor improvement. Fix if time permits."""


def _build_cmd_string(cmd: list[str]) -> str:
    """Convert a command list to a string safe for shell=True."""
    if _IS_WINDOWS:
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def call_model(model: str, prompt: str, timeout: int = 600) -> str:
    """Call an external model CLI using stdin for the prompt."""
    output_file: str | None = None

    try:
        if model == "codex":
            fd, output_file = tempfile.mkstemp(prefix=".ahoy-codex-output-", suffix=".txt")
            os.close(fd)
            cmd = [
                "codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--ephemeral",
                "--output-last-message", output_file, "-",
            ]
            stdin_data = prompt
        elif model == "gemini":
            cmd = ["gemini", "--prompt", "Evaluate the code as instructed below via stdin."]
            stdin_data = prompt
        elif model == "claude":
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
    """Validate that the parsed response contains required objections."""
    if parsed.get("verdict") == "error":
        return parsed

    raw = parsed.get("objections")
    if isinstance(raw, list):
        parsed["objections"] = [o for o in raw if isinstance(o, str) and o.strip()]
    else:
        parsed["objections"] = []

    if not parsed["objections"]:
        print(
            f"[eval_dispatch] WARNING: {model}: objections field missing or empty.",
            file=sys.stderr,
        )
    return parsed


def extract_json(text: str) -> dict | None:
    """Extract JSON from model response."""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    brace_start = text.find("{")
    if brace_start == -1:
        return None

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

    fallback_pattern = re.compile(r"^[-*]\s+`?([^\s`]+\.\w+)`?", re.MULTILINE)
    return list(dict.fromkeys(fallback_pattern.findall(gen_report)))


def collect_code_snippets(sprint_dir: Path, project_root: Path, masker: SensitiveDataMasker | None = None) -> str:
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

    resolved_root = project_root.resolve()
    for file_rel in files[:20]:
        file_path = project_root / file_rel
        try:
            file_path.resolve().relative_to(resolved_root)
        except ValueError:
            print(
                f"[eval_dispatch] WARNING: Skipping '{file_rel}' — resolves outside project root",
                file=sys.stderr,
            )
            continue
        if file_path.exists() and file_path.stat().st_size < 50_000:
            try:
                code = file_path.read_text(encoding="utf-8")
                if masker:
                    code = masker.mask(code)
                snippets.append(f"### {file_rel}\n```\n{code}\n```")
            except (UnicodeDecodeError, OSError):
                pass

    if not snippets:
        raise ValueError("No readable code files from gen_report.md were found under the project root.")

    return "\n\n".join(snippets)


def has_blocker_or_major(issues: list[dict]) -> bool:
    return any(
        issue.get("severity") in {"blocker", "major"}
        or issue.get("priority") in {"P0", "P1"}
        for issue in issues
    )


def derive_status_action(verdict: str, issues: list[dict]) -> str:
    if verdict == "pass":
        return "passed"
    if verdict == "partial_pass":
        return "failed" if has_blocker_or_major(issues) else "passed"
    if verdict == "fail":
        return "failed"
    return "error"


def _error_result(sprint_dir: Path, models: list[str], reason: str) -> dict:
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
    """Merge per-criterion results across models and compute convergence_ratio."""
    all_valid_model_names = list(valid_verdicts.keys())

    per_model: dict[str, list[dict]] = {}
    for model_name, result in valid_verdicts.items():
        cr = result.get("criteria_results")
        if cr and isinstance(cr, list):
            per_model[model_name] = cr

    if not per_model:
        return [], 0.0

    model_names = all_valid_model_names

    all_criteria: dict[str, dict] = {}
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
            cid = cr.get("criterion_id", "").upper()
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
            raw_verdict = cr.get("verdict", "fail")
            model_verdict = str(raw_verdict).lower() if raw_verdict is not None else "fail"
            all_criteria[cid]["model_verdicts"][model_name] = model_verdict
            if model_verdict != "pass":
                all_criteria[cid]["verdict"] = "fail"
            evidence = cr.get("evidence", "")
            if evidence:
                all_criteria[cid]["evidence"].append(f"[{model_name}] {evidence}")

    if not all_criteria:
        return [], 0.0

    for cid, entry in all_criteria.items():
        for model_name in model_names:
            if model_name not in entry["model_verdicts"]:
                entry["model_verdicts"][model_name] = "fail"
                entry["verdict"] = "fail"
                entry["evidence"].append(f"[{model_name}] criterion not reported — treated as fail")

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
    - Valid models fewer than min_valid_models -> error
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

    all_issues = []
    for model_name, result in valid.items():
        for issue in result.get("issues", []):
            issue["found_by"] = model_name
            normalize_issue_priority(issue)
            all_issues.append(issue)

    all_objections: dict[str, list[str]] = {}
    for model_name, result in valid.items():
        model_objections = result.get("objections", [])
        if model_objections:
            all_objections[model_name] = model_objections

    all_failed = set()
    all_passed = set()
    for result in valid.values():
        all_failed.update(result.get("failed_criteria", []))
        all_passed.update(result.get("passed_criteria", []))
    all_passed -= all_failed

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


def load_config() -> dict:
    """Load ahoy_config.json from plugin root if available."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    config: dict = {}
    if plugin_root:
        config_path = Path(plugin_root) / "ahoy_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return config


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
        result = _error_result(sprint_dir, models, "contract.md not found")
        write_result(sprint_dir, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    contract = contract_path.read_text(encoding="utf-8")

    gen_report = ""
    gen_report_path = sprint_dir / "gen_report.md"
    if gen_report_path.exists():
        gen_report = gen_report_path.read_text(encoding="utf-8")

    masking_config = config.get("sensitive_data_masking", {})
    masker = None
    if masking_config.get("enabled", True):
        extra = masking_config.get("extra_patterns", [])
        masker = SensitiveDataMasker(extra_patterns=extra if extra else None)

    try:
        code_snippets = collect_code_snippets(sprint_dir, project_root, masker=masker)
    except ValueError as exc:
        result = _error_result(sprint_dir, models, str(exc))
        write_result(sprint_dir, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    if masker and masker.masked_count > 0:
        print(f"[eval_dispatch] Sensitive data masking: {masker.masked_count} items masked", file=sys.stderr)

    # Build per-model prompts with perspectives
    perspectives = config.get("eval_perspectives", {})
    model_prompts: dict[str, str] = {}
    for model in models:
        p = perspectives.get(model)
        model_prompts[model] = build_eval_prompt(contract, gen_report, code_snippets, perspective=p)

    # Call each model in parallel
    print(f"[eval_dispatch] Evaluation models: {models} (parallel calls)", file=sys.stderr)
    verdicts: dict[str, dict] = {}

    def _call_and_parse(model: str, eval_prompt: str) -> tuple[str, dict]:
        print(f"[eval_dispatch] Calling {model}...", file=sys.stderr)
        raw = call_model(model, eval_prompt, timeout=args.timeout)
        parsed = extract_json(raw)
        if parsed:
            parsed = validate_objections(parsed, model)
            print(f"[eval_dispatch] {model} verdict: {parsed.get('verdict')}", file=sys.stderr)
            return model, parsed
        print(f"[eval_dispatch] {model} raw output (first 500): {raw[:500]}", file=sys.stderr)
        return model, {
            "verdict": "error",
            "error": f"JSON parsing failed. Raw: {raw[:300]}",
            "issues": [],
            "passed_criteria": [],
            "failed_criteria": [],
            "summary": "Response parsing failed",
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {executor.submit(_call_and_parse, m, model_prompts[m]): m for m in models}
        for future in concurrent.futures.as_completed(futures):
            model_name, result = future.result()
            verdicts[model_name] = result

    # Compute consensus
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
    }

    if consensus.get("criteria_results"):
        result["criteria_results"] = consensus["criteria_results"]
        result["convergence_ratio"] = consensus["convergence_ratio"]

    result["status_action"] = derive_status_action(result["verdict"], result["issues"])
    result["model_perspectives"] = {m: perspectives.get(m, "default") for m in models}

    reasoning_chains = {
        name: detail["reasoning_chain"]
        for name, detail in consensus.get("model_verdicts", {}).items()
        if detail.get("reasoning_chain")
    }
    if reasoning_chains:
        result["reasoning_chain"] = reasoning_chains

    if consensus.get("reason"):
        result["error_reason"] = consensus["reason"]

    if masker and masker.masked_count > 0:
        result["masking_report"] = masker.get_mask_report()

    write_result(sprint_dir, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status_action"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
