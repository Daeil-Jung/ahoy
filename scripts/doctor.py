from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_EVALUATORS = (
    "claude",
    "codex",
    "gemini",
)
REQUIRED_PYTHON = (3, 12)


def _run_command(command: list[str], timeout: float) -> CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _extract_version(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    # Keep the parser intentionally permissive: first token sequence that looks like semver.
    match = re.search(r"\d+\.\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?", text)
    if match:
        return match.group(0).lstrip("v")
    return None


def _compare_python_version(version: str | None) -> bool:
    if not version:
        return False
    chunks = version.split(".")
    try:
        major = int(chunks[0])
        minor = int(chunks[1])
    except (IndexError, ValueError):
        return False
    return (major, minor) >= REQUIRED_PYTHON


def _trim_error(value: str, limit: int = 180) -> str:
    text = (value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _error_prefix(kind: str, message: str) -> str:
    return f"{kind}: {_trim_error(message)}" if message else kind


def probe_python(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    required = ">={0}.{1}".format(*REQUIRED_PYTHON)

    for command in ("python3", "python"):
        try:
            result = _run_command([command, "--version"], timeout=timeout)
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            failures.append(
                {
                    "ok": False,
                    "version": None,
                    "required": required,
                    "error": _error_prefix("timeout", f"{command} --version timed out after {timeout:.1f}s"),
                }
            )
            continue

        output = f"{result.stdout} {result.stderr}".strip()
        version = _extract_version(output)
        if result.returncode != 0:
            failures.append(
                {
                    "ok": False,
                    "version": version,
                    "required": required,
                    "error": _error_prefix(
                        "non_zero_exit",
                        f"{command} --version exit code {result.returncode}: {_trim_error(output)}",
                    ),
                }
            )
            continue
        if not version:
            failures.append(
                {
                    "ok": False,
                    "version": version,
                    "required": required,
                    "error": _error_prefix("malformed_version", "Version output does not contain a parseable Python version"),
                }
            )
            continue

        if not _compare_python_version(version):
            failures.append(
                {
                    "ok": False,
                    "version": version,
                    "required": required,
                    "error": f"{command} resolved to Python {version}, below required >= {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}",
                }
            )
            continue

        return {
            "ok": True,
            "version": version,
            "required": required,
            "error": "",
        }

    if failures:
        return failures[-1]

    return {
        "ok": False,
        "version": None,
        "required": required,
        "error": _error_prefix("missing", "python executable is missing from PATH"),
    }


def probe_uv(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    try:
        result = _run_command(["uv", "--version"], timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "version": None, "error": "missing: uv not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "version": None, "error": f"timeout: uv --version exceeded {timeout:.1f}s"}

    output = f"{result.stdout} {result.stderr}".strip()
    version = _extract_version(output)
    if result.returncode != 0:
        return {"ok": False, "version": version, "error": f"non_zero_exit: uv --version exit code {result.returncode}"}
    if not version:
        return {"ok": False, "version": version, "error": "malformed_version: unable to parse uv version"}
    return {"ok": True, "version": version, "error": ""}


def _probe_evaluator(name: str, command: tuple[str, ...], timeout: float) -> dict[str, Any]:
    try:
        result = _run_command(list(command), timeout=timeout)
    except FileNotFoundError:
        return {
            "name": name,
            "installed": False,
            "version_check": "missing",
            "auth_check": "not_checked",
            "usable_for_eval": False,
            "error": "missing: install a supported evaluator CLI and rerun setup",
            "version": None,
            "path": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "installed": True,
            "version_check": "timeout",
            "auth_check": "not_checked",
            "usable_for_eval": False,
            "error": f"timeout: {' '.join(command)} exceeded {timeout:.1f}s",
            "version": None,
            "path": shutil.which(command[0]),
        }

    output = f"{result.stdout} {result.stderr}".strip()
    version = _extract_version(output)
    if result.returncode != 0:
        return {
            "name": name,
            "installed": True,
            "version_check": "failed",
            "auth_check": "not_checked",
            "usable_for_eval": False,
            "error": f"non_zero_exit: {' '.join(command)} exit code {result.returncode}",
            "version": version,
            "path": shutil.which(command[0]),
            "raw_version_output": output,
        }
    if not version:
        return {
            "name": name,
            "installed": True,
            "version_check": "failed",
            "auth_check": "not_checked",
            "usable_for_eval": False,
            "error": "malformed_version: version output did not include a parseable semver",
            "version": version,
            "path": shutil.which(command[0]),
            "raw_version_output": output,
        }

    return {
        "name": name,
        "installed": True,
        "version_check": "ok",
        "auth_check": "unknown",
        "usable_for_eval": False,
        "error": "auth_unknown: version command succeeded, but evaluator authentication was not verified",
        "version": version,
        "path": shutil.which(command[0]),
        "raw_version_output": output,
    }


def _default_evaluators() -> list[tuple[str, tuple[str, ...]]]:
    return [(name, (name, "--version")) for name in DEFAULT_EVALUATORS]


def run_diagnostics(
    project_root: Path,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    evaluators: list[tuple[str, tuple[str, ...]]] | None = None,
) -> dict[str, Any]:
    _ = project_root
    timeout = max(0.1, float(timeout))
    evaluator_specs = evaluators or _default_evaluators()

    python = probe_python(timeout=timeout)
    uv = probe_uv(timeout=timeout)

    evaluated = [_probe_evaluator(name, command, timeout=timeout) for name, command in evaluator_specs]

    usable = [entry["name"] for entry in evaluated if entry.get("usable_for_eval")]
    if len(usable) == 0:
        recommendation = {
            "mode": "blocked",
            "eval_models": [],
            "min_models": 0,
            "strict_gate_warning": "No usable external evaluators found. Configure at least one evaluator before running evaluation.",
            "reason": "No evaluators returned version_check=ok",
        }
    elif len(usable) == 1:
        recommendation = {
            "mode": "advisory",
            "eval_models": usable,
            "min_models": 1,
            "strict_gate_warning": "Strict consensus mode requires at least 2 usable evaluators.",
            "reason": "One usable evaluator detected: advisory mode only.",
        }
    else:
        recommendation = {
            "mode": "strict",
            "eval_models": usable,
            "min_models": 2,
            "strict_gate_warning": "",
            "reason": "At least two usable evaluators are available.",
        }

    return {
        "python": {
            "ok": python["ok"],
            "version": python["version"],
            "required": python["required"],
            "error": python["error"],
        },
        "uv": {
            "ok": uv["ok"],
            "version": uv["version"],
            "error": uv["error"],
        },
        "evaluators": evaluated,
        "recommendation": recommendation,
    }


def _render_table(result: dict[str, Any]) -> str:
    lines = [
        "AHOY environment diagnostics",
        "",
        f"Python:  {'OK' if result['python']['ok'] else 'FAIL'} "
        f"(required {result['python']['required']}, found {result['python']['version']})",
        f"UV:     {'OK' if result['uv']['ok'] else 'FAIL'} "
        f"(found {result['uv']['version']})",
        "",
        "Evaluators:",
    ]
    for entry in result["evaluators"]:
        status = "OK" if entry["usable_for_eval"] else "NO"
        detail = entry["error"] or "usable"
        lines.append(f"  - {entry['name']}: {status} ({entry['version_check']}) - {detail}")

    rec = result["recommendation"]
    warning = rec.get("strict_gate_warning")
    lines += [
        "",
        f"Recommendation: {rec['mode']}",
        f"Models: {', '.join(rec['eval_models']) if rec['eval_models'] else '(none)'}",
        f"min_models: {rec['min_models']}",
    ]
    if warning:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose AHOY environment readiness before setup/evaluation.",
    )
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_diagnostics(args.project_root, timeout=max(0.1, args.timeout))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_table(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
