from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from conftest import load_module


doctor = load_module("test_doctor_module", "scripts/doctor.py")


def make_fake_python_stub(path: Path, content: str) -> tuple[str, str]:
    path.write_text(content, encoding="utf-8")
    return (sys.executable, str(path))


def run_with_fake_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra_paths: list[str] | None = None) -> None:
    paths = [str(tmp_path)]
    if extra_paths:
        paths.extend(extra_paths)
    paths.append(os.environ.get("PATH", ""))
    monkeypatch.setenv("PATH", os.pathsep.join(filter(None, paths)))


def test_timeout_evaluator_probe_is_distinct(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    command = make_fake_python_stub(
        tmp_path / "codex_stub.py",
        "import time\ntime.sleep(2)\nprint('codex 0.9.0')\n",
    )
    run_with_fake_path(tmp_path, monkeypatch, [])

    start = time.perf_counter()
    result = doctor.run_diagnostics(
        tmp_path,
        timeout=0.2,
        evaluators=[("codex", command)],
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0
    assert result["evaluators"][0]["version_check"] == "timeout"
    assert result["evaluators"][0]["usable_for_eval"] is False
    assert result["recommendation"]["mode"] == "blocked"


def test_missing_and_bad_evaluator_states(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad_exit = make_fake_python_stub(tmp_path / "bad_exit.py", "import sys\nsys.exit(1)\n")
    bad_version = make_fake_python_stub(tmp_path / "bad_version.py", "print('not-a-version')\n")
    run_with_fake_path(tmp_path, monkeypatch, [])

    result = doctor.run_diagnostics(
        tmp_path,
        timeout=2,
        evaluators=[
            ("missing", ("missing", "--version")),
            ("bad_exit", bad_exit),
            ("bad_version", bad_version),
        ],
    )

    by_name = {entry["name"]: entry for entry in result["evaluators"]}

    assert by_name["missing"]["version_check"] == "missing"
    assert by_name["missing"]["installed"] is False
    assert "malformed" not in by_name["missing"]["error"]

    assert by_name["bad_exit"]["version_check"] == "failed"
    assert by_name["bad_exit"]["installed"] is True
    assert "non_zero_exit" in by_name["bad_exit"]["error"]

    assert by_name["bad_version"]["version_check"] == "failed"
    assert by_name["bad_version"]["installed"] is True
    assert "malformed_version" in by_name["bad_version"]["error"]


def test_version_only_evaluator_is_not_eval_usable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    command = make_fake_python_stub(tmp_path / "codex_stub.py", "print('codex 0.5.0')\n")
    run_with_fake_path(tmp_path, monkeypatch, [])

    result = doctor.run_diagnostics(
        tmp_path,
        timeout=1,
        evaluators=[("codex", command)],
    )

    evaluator = result["evaluators"][0]
    assert evaluator["version_check"] == "ok"
    assert evaluator["auth_check"] == "unknown"
    assert evaluator["usable_for_eval"] is False
    assert "auth_unknown" in evaluator["error"]
    assert result["recommendation"]["mode"] == "blocked"


def test_python_probe_falls_back_after_unsupported_python3(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], timeout: float) -> object:
        executable = command[0]
        if executable == "python3":
            return type("Result", (), {"stdout": "Python 3.11.8", "stderr": "", "returncode": 0})()
        if executable == "python":
            return type("Result", (), {"stdout": "Python 3.12.1", "stderr": "", "returncode": 0})()
        raise AssertionError(executable)

    monkeypatch.setattr(doctor, "_run_command", fake_run)

    result = doctor.probe_python(timeout=1)

    assert result["ok"] is True
    assert result["version"] == "3.12.1"


@pytest.mark.parametrize(
    "usable_count, expected_mode, expected_min",
    [
        (0, "blocked", 0),
        (1, "advisory", 1),
        (2, "strict", 2),
    ],
)
def test_recommendation_modes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, usable_count: int, expected_mode: str, expected_min: int) -> None:
    specs = [(f"eval_{i}", (f"eval_{i}", "--version")) for i in range(2)]

    def fake_probe(name: str, command: tuple[str, ...], timeout: float) -> dict[str, object]:
        index = int(name.rsplit("_", 1)[1])
        usable = index < usable_count
        return {
            "name": name,
            "installed": True,
            "version_check": "ok",
            "auth_check": "ok" if usable else "failed",
            "usable_for_eval": usable,
            "error": "" if usable else "auth_failed",
            "version": "0.0.1",
            "path": command[0],
        }

    monkeypatch.setattr(doctor, "_probe_evaluator", fake_probe)
    result = doctor.run_diagnostics(tmp_path, timeout=2, evaluators=specs)

    assert result["recommendation"]["mode"] == expected_mode
    assert result["recommendation"]["min_models"] == expected_min
    assert len(result["recommendation"]["eval_models"]) == usable_count


def test_doctor_json_schema_includes_setup_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    command = make_fake_python_stub(tmp_path / "codex_stub.py", "print('codex 0.5.0')\n")
    run_with_fake_path(tmp_path, monkeypatch, [])

    payload = doctor.run_diagnostics(
        tmp_path,
        timeout=1,
        evaluators=[("codex", command)],
    )
    dumped = json.loads(json.dumps(payload))

    assert isinstance(dumped, dict)
    assert {"python", "uv", "evaluators", "recommendation"}.issubset(dumped)
    assert isinstance(dumped["evaluators"], list)
    first = dumped["evaluators"][0]
    assert set(["name", "installed", "version_check", "auth_check", "usable_for_eval", "error"]).issubset(first)
    assert dumped["recommendation"]["mode"] in {"blocked", "advisory", "strict"}


ROOT = Path(__file__).resolve().parents[1]


def test_setup_skill_contract_is_documented() -> None:
    content = (ROOT / "skills/ahoy-setup/SKILL.md").read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" in content
    assert "python scripts/doctor.py --project-root ." not in content
    assert "recommendation" in content
    assert "Python | 3.12+" in content or "Required: 3.12+" in content


def test_setup_skill_contract_respects_advisory_min_models() -> None:
    content = (ROOT / "skills/ahoy-setup/SKILL.md").read_text(encoding="utf-8")

    lowered = content.lower()
    assert "at least 2 required" not in lowered
    assert "at least 2 must be present for consensus evaluation" not in lowered
    assert "최소 2개" not in content

    assert "advisory" in lowered
    assert "strict" in lowered
    assert "min_models" in content
    assert '"min_models": 1' in content
    assert '"min_models": 2' in content

    section = content[content.index("AskUserQuestion"):]
    assert '"codex"' in section and '"gemini"' in section and '"claude"' in section
    assert '"codex, gemini"' in section
    assert '"codex, claude"' in section
    assert '"gemini, claude"' in section
    assert '"codex, gemini, claude (all)"' in section
    assert "# Advisory example (min_models = 1)" in content
    assert "# Strict example (consensus mode, min_models = 2)" in content
    assert '"eval_models": ["claude"]' in content
    assert '"eval_models": ["codex", "gemini"]' in content


def test_python_requirement_wiring_matches_readme_and_setup_docs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docko = (ROOT / "docs/README.ko.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    setup = (ROOT / "skills/ahoy-setup/SKILL.md").read_text(encoding="utf-8")

    assert "3.12+" in readme
    assert "3.12+" in docko
    assert "3.12" in claude
    assert "3.12+" in setup
