#!/usr/bin/env python3
"""Harness state transition validation script.

Called from Claude Code hooks to block harness rule violations.
Supports extended verification: test_command, lint_command, type_check_command, and coverage_threshold.

Usage: validate_harness.py <check_type>
  check_type:
    scope-check          — Before Edit/Write: verify target file is within contract.md Implementation Scope
    pre-state-write      — Before writing harness_state.json: verify external evaluation exists before leaving generated
    post-state-write     — After writing harness_state.json: verify status=passed <-> status_action consistency
    pre-gen              — Before Generator execution: verify contract.md exists
    post-eval            — After evaluation: verify external model verdict in issues.json
    guard-eval-files     — Block direct writing of issues.json (only eval_dispatch.py allowed)
    audit-final-scope    — Before generated transition: verify all modified files are within contract scope
    pre-commit           — Run tests, lint, and type check before commit (only in harness mode)
    pre-push             — Run tests, lint, type check + verify state consistency before push
    post-edit-quality    — After Edit/Write: detect TODO/FIXME/stub/placeholder patterns
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HARNESS_DIR = Path(".claude/harness")
STATE_FILE = HARNESS_DIR / "harness_state.json"


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_state() -> dict:
    return load_json(STATE_FILE) or {}


def get_current_sprint(state: dict) -> str:
    idx = state.get("current_sprint_index", 0)
    sprints = state.get("sprints", [])
    if idx < len(sprints):
        return sprints[idx].get("sprint_id", "")
    return ""


def get_current_status(state: dict) -> str:
    idx = state.get("current_sprint_index", 0)
    sprints = state.get("sprints", [])
    if idx < len(sprints):
        return sprints[idx].get("status", "")
    return ""


def _read_spec_content() -> str:
    spec_file = HARNESS_DIR / "spec.md"
    if not spec_file.exists():
        return ""
    return spec_file.read_text(encoding="utf-8")


def _is_placeholder(value: str) -> bool:
    return "{{" in value


def get_test_command() -> str:
    content = _read_spec_content()
    if not content:
        return ""
    match = re.search(r'test_command:\s*"([^"]+)"', content)
    if match and not _is_placeholder(match.group(1)):
        return match.group(1)
    return ""


def get_lint_command() -> str:
    content = _read_spec_content()
    if not content:
        return ""
    match = re.search(r'lint_command:\s*"([^"]+)"', content)
    if match and not _is_placeholder(match.group(1)):
        return match.group(1)
    return ""


def get_type_check_command() -> str:
    content = _read_spec_content()
    if not content:
        return ""
    match = re.search(r'type_check_command:\s*"([^"]+)"', content)
    if match and not _is_placeholder(match.group(1)):
        return match.group(1)
    return ""


def get_coverage_threshold() -> int | None:
    content = _read_spec_content()
    if not content:
        return None
    match = re.search(r'coverage_threshold:\s*(\S+)', content)
    if not match or _is_placeholder(match.group(1)):
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _parse_coverage_percent(output: str) -> float | None:
    """Extract coverage percentage from test output.

    Looks for common patterns like:
      - "Coverage: 85%"
      - "85% coverage"
      - "TOTAL ... 85%"
      - "Total coverage: 85.3%"
    """
    patterns = [
        r'(?:coverage|cov)[:\s]+(\d+(?:\.\d+)?)\s*%',
        r'(\d+(?:\.\d+)?)\s*%\s*(?:coverage|cov)',
        r'TOTAL\s+.*?(\d+(?:\.\d+)?)\s*%',
        r'(\d+(?:\.\d+)?)\s*%',
    ]
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _run_verification_command(label: str, cmd: str) -> None:
    """Run a verification command and fail with a clear message if it fails."""
    info(f"[HARNESS-GUARD] Running {label}: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        fail(
            f"\n[HARNESS-GUARD] Blocked: {label} failed — blocked\n"
            f"[HARNESS-GUARD] Fix the {label} issues and try again."
        )
    info(f"[HARNESS-GUARD] Passed: {label} passed")


def _run_tests_with_coverage(test_cmd: str, coverage_threshold: int | None) -> None:
    """Run test command, optionally checking coverage threshold."""
    info(f"[HARNESS-GUARD] Running tests: {test_cmd}")
    result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)
    # Print output so it's visible
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        fail(
            "\n[HARNESS-GUARD] Blocked: Tests failed — blocked\n"
            "[HARNESS-GUARD] Fix the tests and try again."
        )
    info("[HARNESS-GUARD] Passed: Tests passed")

    if coverage_threshold is not None:
        combined_output = (result.stdout or "") + (result.stderr or "")
        coverage = _parse_coverage_percent(combined_output)
        if coverage is not None:
            if coverage < coverage_threshold:
                fail(
                    f"\n[HARNESS-GUARD] Blocked: Coverage {coverage:.1f}% is below threshold {coverage_threshold}%\n"
                    "[HARNESS-GUARD] Increase test coverage and try again."
                )
            info(f"[HARNESS-GUARD] Passed: Coverage {coverage:.1f}% meets threshold {coverage_threshold}%")
        else:
            info(f"[HARNESS-GUARD] Warning: Could not parse coverage from test output — skipping coverage check (threshold: {coverage_threshold}%)")


def verify_issues_integrity(issues_file: Path) -> str:
    if not issues_file.exists():
        return "FAIL:file_not_found"
    data = load_json(issues_file)
    if data is None:
        return "FAIL:parse_error"
    required = ["evaluated_at", "models_used", "models_valid", "verdict", "model_verdicts", "status_action"]
    missing = [k for k in required if k not in data]
    if missing:
        return f"FAIL:missing_fields:{','.join(missing)}"
    if not data.get("evaluated_at", "").startswith("20"):
        return "FAIL:invalid_timestamp"
    return "OK"


def get_valid_model_count(issues_file: Path) -> int:
    data = load_json(issues_file)
    if data is None:
        return 0
    return len(data.get("models_valid", []))


def get_verdict(issues_file: Path) -> str:
    data = load_json(issues_file)
    if data is None:
        return "unknown"
    return data.get("verdict", "unknown")


def get_status_action(issues_file: Path) -> str:
    data = load_json(issues_file)
    if data is None:
        return "unknown"
    return data.get("status_action", "unknown")


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    print(msg)


# ── Check handlers ──────────────────────────────────────────────


def check_pre_state_write() -> None:
    """Validation before writing harness_state.json."""
    # Create backup for rollback (used by post-state-write)
    try:
        shutil.copy2(STATE_FILE, f"{STATE_FILE}.bak")
    except OSError:
        pass

    state = load_state()
    current_sprint = get_current_sprint(state)
    current_status = get_current_status(state)

    if not current_sprint:
        return  # No sprints yet, initialization phase
    if current_status != "generated":
        return  # Transitions from non-generated states don't require evaluation

    # State change from generated state -> external evaluation must exist
    issues_file = HARNESS_DIR / "sprints" / current_sprint / "issues.json"
    integrity = verify_issues_integrity(issues_file)

    if integrity == "FAIL:file_not_found":
        fail(
            "[HARNESS-GUARD] Blocked: Attempted transition from generated state without external evaluation\n"
            "[HARNESS-GUARD] Run eval_dispatch.py first."
        )
    if integrity.startswith("FAIL:"):
        fail(
            f"[HARNESS-GUARD] Blocked: issues.json integrity check failed: {integrity}\n"
            "[HARNESS-GUARD] This is not a valid file generated by eval_dispatch.py."
        )

    valid_count = get_valid_model_count(issues_file)
    if valid_count < 2:
        fail(
            f"[HARNESS-GUARD] Blocked: {valid_count} valid external model(s) — minimum 2 required\n"
            "[HARNESS-GUARD] Cannot transition state with single-model evaluation only."
        )

    info(f"[HARNESS-GUARD] Passed: External evaluation confirmed (valid models: {valid_count}) — state transition allowed")


def check_post_state_write() -> None:
    """Consistency check after writing harness_state.json."""
    state = load_state()
    current_sprint = get_current_sprint(state)
    current_status = get_current_status(state)
    bak = Path(f"{STATE_FILE}.bak")

    if not current_sprint or current_status != "passed":
        bak.unlink(missing_ok=True)
        return

    issues_file = HARNESS_DIR / "sprints" / current_sprint / "issues.json"
    need_rollback = False

    if not issues_file.exists():
        info("[HARNESS-GUARD] CRITICAL: status=passed but issues.json not found")
        need_rollback = True

    if not need_rollback:
        verdict = get_verdict(issues_file)
        status_action = get_status_action(issues_file)
        if status_action != "passed":
            info(f"[HARNESS-GUARD] CRITICAL: status=passed but status_action={status_action} (verdict={verdict})")
            need_rollback = True

    if need_rollback:
        if bak.exists():
            shutil.copy2(bak, STATE_FILE)
            bak.unlink(missing_ok=True)
            info("[HARNESS-GUARD] Auto-rollback complete — harness_state.json restored to previous state.")
            info("[HARNESS-GUARD] Record the correct state matching the external evaluation verdict.")
        else:
            info("[HARNESS-GUARD] Warning: No backup file — auto-rollback not possible. Manually fix harness_state.json.")
        sys.exit(1)

    bak.unlink(missing_ok=True)
    info(f"[HARNESS-GUARD] Passed: State consistency confirmed (status=passed, verdict={verdict})")


def check_guard_eval_files() -> None:
    """Block direct writing to issues.json."""
    fail(
        "[HARNESS-GUARD] Blocked: Only eval_dispatch.py can write issues.json.\n"
        "[HARNESS-GUARD] Direct creation/modification of issues.json by Claude compromises evaluation integrity.\n"
        "[HARNESS-GUARD] If external model evaluation is needed, run eval_dispatch.py via Bash."
    )


def check_pre_gen() -> None:
    """Verify contract.md exists before Generator execution."""
    state = load_state()
    current_sprint = get_current_sprint(state)
    contract = HARNESS_DIR / "sprints" / current_sprint / "contract.md"

    if not contract.exists():
        fail(
            f"[HARNESS-GUARD] Blocked: Contract not found: {contract}\n"
            "[HARNESS-GUARD] Run /ahoy:ahoy-plan first."
        )
    info("[HARNESS-GUARD] Passed: Sprint contract confirmed")


def check_post_eval() -> None:
    """Verify issues.json validity after evaluation."""
    state = load_state()
    current_sprint = get_current_sprint(state)
    issues_file = HARNESS_DIR / "sprints" / current_sprint / "issues.json"

    if not issues_file.exists():
        fail("[HARNESS-GUARD] Blocked: Evaluation result file not found")

    verdict = get_verdict(issues_file)
    status_action = get_status_action(issues_file)
    info(f"[HARNESS-GUARD] External evaluation verdict: {verdict} (status_action={status_action})")

    if verdict in ("error", "unknown"):
        data = load_json(issues_file) or {}
        reason = data.get("error_reason", "Unknown cause")
        fail(
            f"[HARNESS-GUARD] Blocked: External model evaluation failed: {reason}\n"
            "[HARNESS-GUARD] Cannot proceed without valid external model evaluation."
        )

    valid_count = get_valid_model_count(issues_file)
    if valid_count < 2:
        fail(
            f"[HARNESS-GUARD] Blocked: {valid_count} valid model(s) — minimum 2 required\n"
            "[HARNESS-GUARD] Consensus cannot be established with single-model evaluation only."
        )

    info(f"[HARNESS-GUARD] Passed: External evaluation valid (verdict: {verdict}, valid models: {valid_count})")


def check_pre_commit() -> None:
    """Run tests, lint, and type check before commit (enforced only in harness mode)."""
    test_cmd = get_test_command()
    lint_cmd = get_lint_command()
    type_cmd = get_type_check_command()
    threshold = get_coverage_threshold()

    if test_cmd:
        _run_tests_with_coverage(test_cmd, threshold)

    if lint_cmd:
        _run_verification_command("lint", lint_cmd)

    if type_cmd:
        _run_verification_command("type check", type_cmd)

    if test_cmd or lint_cmd or type_cmd:
        info("[HARNESS-GUARD] Passed: All verification checks passed — commit allowed")


def check_pre_push() -> None:
    """Run tests, lint, type check + verify harness state consistency before push."""
    # 1. Run tests, lint, type check
    test_cmd = get_test_command()
    lint_cmd = get_lint_command()
    type_cmd = get_type_check_command()
    threshold = get_coverage_threshold()

    if test_cmd:
        _run_tests_with_coverage(test_cmd, threshold)

    if lint_cmd:
        _run_verification_command("lint", lint_cmd)

    if type_cmd:
        _run_verification_command("type check", type_cmd)

    # 2. Harness state consistency check
    state = load_state()
    problems = []
    for sprint in state.get("sprints", []):
        sid = sprint.get("sprint_id", "")
        status = sprint.get("status", "")
        if status == "passed":
            issues_path = HARNESS_DIR / "sprints" / sid / "issues.json"
            if not issues_path.exists():
                problems.append(f"{sid}: passed but issues.json not found")
                continue
            data = load_json(issues_path) or {}
            verdict = data.get("verdict", "unknown")
            status_action = data.get("status_action", "unknown")
            if status_action != "passed":
                problems.append(f"{sid}: passed but status_action={status_action} (verdict={verdict})")

    if problems:
        fail(
            "[HARNESS-GUARD] Blocked: Harness state inconsistency detected:\n"
            + "\n".join(problems)
            + "\n[HARNESS-GUARD] Fix the state and try pushing again."
        )

    info("[HARNESS-GUARD] Passed: Harness state consistency confirmed — push allowed")


def _path_matches_scope_entry(file_path: str, scope_entry: str) -> bool:
    """Check whether *file_path* matches a single scope entry.

    Both values must already be forward-slash normalised.
    """
    return (
        file_path == scope_entry
        or file_path.endswith("/" + scope_entry)
        or scope_entry in file_path
    )


def parse_scope_from_contract(contract_path: Path) -> tuple[list[str], list[str], list[str]]:
    """Parse Implementation Scope from contract.md.

    Returns (files_to_create, files_to_modify, files_to_preserve).
    """
    try:
        content = contract_path.read_text(encoding="utf-8")
    except OSError:
        return [], [], []

    create: list[str] = []
    modify: list[str] = []
    preserve: list[str] = []

    current_section: list[str] | None = None
    in_scope = False

    for line in content.splitlines():
        stripped = line.strip()

        # Detect top-level heading that ends the scope block
        if in_scope and re.match(r"^##\s+", stripped) and "Implementation Scope" not in stripped:
            break

        if re.match(r"^##\s+Implementation Scope", stripped):
            in_scope = True
            continue

        if not in_scope:
            continue

        if re.match(r"^###\s+Files to Create", stripped):
            current_section = create
            continue
        elif re.match(r"^###\s+Files to Modify", stripped):
            current_section = modify
            continue
        elif re.match(r"^###\s+Files to Preserve", stripped):
            current_section = preserve
            continue
        elif re.match(r"^###\s+", stripped):
            current_section = None
            continue

        if current_section is not None:
            match = re.match(r"^[-*]\s+`?([^`\s]+)`?", stripped)
            if match:
                current_section.append(match.group(1))

    return create, modify, preserve


def check_scope() -> None:
    """Verify target file is within contract.md Implementation Scope."""
    state = load_state()
    current_sprint = get_current_sprint(state)

    if not current_sprint:
        return  # No active sprint, pass through

    contract_path = HARNESS_DIR / "sprints" / current_sprint / "contract.md"
    if not contract_path.exists():
        return  # No contract yet, pass through

    # Get the file path from CLAUDE_TOOL_INPUT
    tool_input_raw = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not tool_input_raw:
        return  # No tool input, pass through

    try:
        tool_input = json.loads(tool_input_raw)
    except json.JSONDecodeError:
        return  # Can't parse, pass through

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    # Normalize to forward slashes for consistent comparison
    file_path_normalized = file_path.replace("\\", "/")

    # Always allow harness files
    if ".claude/harness/" in file_path_normalized or ".claude/harness\\" in file_path:
        return

    # Parse the allowed scope
    create, modify, preserve = parse_scope_from_contract(contract_path)

    # Files to Preserve are explicitly blocked
    for p in preserve:
        if _path_matches_scope_entry(file_path_normalized, p.replace("\\", "/")):
            fail(
                f"[HARNESS-GUARD] Blocked: '{file_path}' is listed in Files to Preserve\n"
                "[HARNESS-GUARD] This file is protected by the sprint contract and must not be modified."
            )

    # Allowed files = create + modify
    allowed = create + modify
    if not allowed:
        return  # No scope defined, pass through

    for p in allowed:
        if _path_matches_scope_entry(file_path_normalized, p.replace("\\", "/")):
            return  # File is in scope

    # Check if file is part of the AHOY plugin itself — always allow
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        plugin_normalized = plugin_root.replace("\\", "/")
        if file_path_normalized.startswith(plugin_normalized):
            return

    fail(
        f"[HARNESS-GUARD] Blocked: '{file_path}' is outside the Implementation Scope\n"
        f"[HARNESS-GUARD] Allowed files: {', '.join(allowed)}\n"
        "[HARNESS-GUARD] Only create/modify files specified in the sprint contract."
    )


def audit_final_scope() -> None:
    """Audit all modified files against contract scope before generated transition.

    Complements check_scope() (per-file Edit/Write guard) by scanning the full
    git diff at state-transition time so nothing slips through.
    """
    state = load_state()
    current_sprint = get_current_sprint(state)
    current_status = get_current_status(state)

    if not current_sprint:
        return  # No active sprint
    if current_status != "generated":
        return  # Only audit on transitions from generated state

    contract_path = HARNESS_DIR / "sprints" / current_sprint / "contract.md"
    if not contract_path.exists():
        return  # No contract yet

    create, modify, preserve = parse_scope_from_contract(contract_path)
    allowed = create + modify
    if not allowed and not preserve:
        return  # No scope defined, pass through

    # Check if HEAD exists (fresh repos have no commits)
    head_check = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True,
    )
    if head_check.returncode != 0:
        print("[validate_harness] audit_final_scope: HEAD not found (unborn repo), skipping scope audit", file=sys.stderr)
        return

    # Collect changed files via git diff against HEAD
    git_commands = [
        ("git diff", ["git", "diff", "--name-only", "HEAD"]),
        ("git diff --cached", ["git", "diff", "--name-only", "--cached"]),
        ("git ls-files", ["git", "ls-files", "--others", "--exclude-standard"]),
    ]

    outputs: list[str] = []
    for label, cmd in git_commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as exc:
            fail(
                f"[HARNESS-GUARD] Blocked: Failed to collect git scope ({label}: {exc}) "
                "— cannot verify file changes, blocking transition"
            )
            return  # unreachable; helps static analysis see proc is always bound
        if proc.returncode != 0:
            stderr_hint = (proc.stderr or "").strip()[:200]
            fail(
                f"[HARNESS-GUARD] Blocked: Failed to collect git scope ({label} exited {proc.returncode}"
                f"{': ' + stderr_hint if stderr_hint else ''}) "
                "— cannot verify file changes, blocking transition"
            )
        outputs.append(proc.stdout)

    changed_files: set[str] = set()
    for output in outputs:
        for line in output.strip().splitlines():
            stripped = line.strip()
            if stripped:
                changed_files.add(stripped.replace("\\", "/"))

    # Filter out harness-internal files and plugin-root files — always allowed
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    plugin_root_normalized = plugin_root.replace("\\", "/") if plugin_root else ""
    user_changed = [
        f for f in sorted(changed_files)
        if not f.startswith(".claude/harness/")
        and not (plugin_root_normalized and f.startswith(plugin_root_normalized))
    ]

    # Check preserved files for unauthorized modifications
    preserved_violations = [
        f for f in user_changed
        if any(_path_matches_scope_entry(f, p.replace("\\", "/")) for p in preserve)
    ]

    if preserved_violations:
        fail(
            "[HARNESS-GUARD] Blocked: Files to Preserve were modified:\n"
            + "\n".join(f"  - {f}" for f in preserved_violations)
            + "\n[HARNESS-GUARD] These files are protected by the sprint contract and must not be modified.\n"
            "[HARNESS-GUARD] Revert changes to preserved files before transitioning."
        )

    # Check for files outside the allowed scope (create + modify)
    out_of_scope: list[str] = []
    if allowed:
        out_of_scope = [
            f for f in user_changed
            if not any(_path_matches_scope_entry(f, p.replace("\\", "/")) for p in allowed)
        ]

    if out_of_scope:
        fail(
            "[HARNESS-GUARD] Blocked: Intent-Action mismatch — files outside contract scope were modified:\n"
            + "\n".join(f"  - {f}" for f in out_of_scope)
            + f"\n[HARNESS-GUARD] Allowed scope: {', '.join(allowed)}\n"
            "[HARNESS-GUARD] Revert out-of-scope changes or update the contract before transitioning to generated."
        )

    info("[HARNESS-GUARD] Passed: All modified files are within contract scope")


# ── Post-edit quality patterns ─────────────────────────────────

_TEST_FILE_PATTERNS = (
    "test_",
    "_test.py",
    "/tests/",
    "/__tests__/",
    ".test.",
    ".spec.",
)

_MARKER_PATTERN = re.compile(
    r"\b(TODO|FIXME|HACK|XXX)\b",
)

_STUB_PATTERNS = [
    re.compile(r"^\s*pass\s*$"),
    re.compile(r"^\s*\.\.\.\s*$"),
    re.compile(r"""throw\s+new\s+Error\s*\(\s*["']not implemented["']\s*\)""", re.IGNORECASE),
    re.compile(r"""raise\s+NotImplementedError"""),
]

_PLACEHOLDER_PATTERN = re.compile(
    r"\b(lorem|foo|bar|baz|test123|placeholder)\b",
    re.IGNORECASE,
)


def _is_test_file(file_path: str) -> bool:
    """Return True if *file_path* (forward-slash normalized) looks like a test file."""
    # Ensure a leading slash so directory patterns like "/tests/" match relative paths
    normalized = "/" + file_path.lstrip("/")
    return any(pat in normalized for pat in _TEST_FILE_PATTERNS)


def _load_allowlist() -> set[str]:
    """Load allowed patterns from .ahoy-allowlist (one pattern per line)."""
    allowlist: set[str] = set()
    allowlist_path = Path(".ahoy-allowlist")
    if allowlist_path.exists():
        for raw_line in allowlist_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                allowlist.add(line)
    return allowlist


def _line_allowed(line: str, allowlist: set[str]) -> bool:
    """Return True if *line* matches any entry in the allowlist."""
    return any(entry in line for entry in allowlist)


def check_post_edit_quality() -> None:
    """Detect TODO/FIXME/stub/placeholder patterns injected by Edit/Write."""
    tool_input_raw = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not tool_input_raw:
        return

    try:
        tool_input = json.loads(tool_input_raw)
    except json.JSONDecodeError:
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    # Normalize path separators for consistent matching
    file_path_normalized = file_path.replace("\\", "/")

    # Skip test files — patterns like TODO/placeholder are acceptable there
    if _is_test_file(file_path_normalized):
        return

    # Skip non-text / binary-likely extensions
    text_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
        ".kt", ".scala", ".sh", ".bash", ".zsh", ".ps1",
        ".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css",
        ".md", ".txt", ".cfg", ".ini", ".env", ".sql",
    }
    ext = Path(file_path).suffix.lower()
    if ext and ext not in text_extensions:
        return

    # Scan only the content being written — not the entire file on disk.
    # For Edit tool: inspect new_string; for Write tool: inspect content.
    content = tool_input.get("new_string") or tool_input.get("content") or ""
    if not content:
        return

    allowlist = _load_allowlist()
    violations: list[str] = []

    for lineno, line in enumerate(content.splitlines(), start=1):
        if _line_allowed(line, allowlist):
            continue

        # Check TODO/FIXME/HACK/XXX markers
        marker_match = _MARKER_PATTERN.search(line)
        if marker_match:
            violations.append(f"  L{lineno}: {marker_match.group()} marker — {line.strip()}")
            continue

        # Check stub-only implementations
        for stub_re in _STUB_PATTERNS:
            if stub_re.search(line):
                violations.append(f"  L{lineno}: stub pattern — {line.strip()}")
                break
        else:
            # Check placeholder strings
            ph_match = _PLACEHOLDER_PATTERN.search(line)
            if ph_match:
                violations.append(f"  L{lineno}: placeholder '{ph_match.group()}' — {line.strip()}")

    if violations:
        detail = "\n".join(violations[:20])  # cap output length
        extra = ""
        if len(violations) > 20:
            extra = f"\n  ... and {len(violations) - 20} more"
        fail(
            f"[HARNESS-GUARD] Blocked: Quality issues detected in '{file_path}':\n"
            f"{detail}{extra}\n"
            "[HARNESS-GUARD] Remove TODO/FIXME markers, stubs, and placeholders before saving.\n"
            "[HARNESS-GUARD] If intentional, add the pattern to .ahoy-allowlist."
        )

    info(f"[HARNESS-GUARD] Passed: Post-edit quality check — '{file_path}'")


# ── Main ────────────────────────────────────────────────────────

CHECKS = {
    "scope-check": check_scope,
    "pre-state-write": check_pre_state_write,
    "post-state-write": check_post_state_write,
    "pre-gen": check_pre_gen,
    "post-eval": check_post_eval,
    "guard-eval-files": check_guard_eval_files,
    "audit-final-scope": audit_final_scope,
    "pre-commit": check_pre_commit,
    "pre-push": check_pre_push,
    "post-edit-quality": check_post_edit_quality,
}


def main() -> None:
    # If .claude/harness doesn't exist, not in harness mode -> pass through
    if not HARNESS_DIR.is_dir() or not STATE_FILE.is_file():
        sys.exit(0)

    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        valid = "|".join(CHECKS)
        print(f"Usage: validate_harness.py <{valid}>")
        sys.exit(1)

    CHECKS[sys.argv[1]]()


if __name__ == "__main__":
    main()
