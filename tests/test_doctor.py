from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from conftest import load_module


doctor = load_module("test_doctor_module", "scripts/doctor.py")


def make_fake_executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def run_with_fake_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra_paths: list[str] | None = None) -> None:
    paths = [str(tmp_path)]
    if extra_paths:
        paths.extend(extra_paths)
    paths.append(os.environ.get("PATH", ""))
    monkeypatch.setenv("PATH", ":".join(filter(None, paths)))


def test_timeout_evaluator_probe_is_distinct(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "codex"
    make_fake_executable(
        fake,
        "#!/usr/bin/env sh\nsleep 2\nprintf 'codex 0.9.0'\n",
    )
    run_with_fake_path(tmp_path, monkeypatch, [])

    start = time.perf_counter()
    result = doctor.run_diagnostics(
        tmp_path,
        timeout=0.2,
        evaluators=[("codex", ("codex", "--version"))],
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0
    assert result["evaluators"][0]["version_check"] == "timeout"
    assert result["evaluators"][0]["usable_for_eval"] is False
    assert result["recommendation"]["mode"] == "blocked"


def test_missing_and_bad_evaluator_states(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    make_fake_executable(
        tmp_path / "bad_exit",
        "#!/usr/bin/env sh\nexit 1\n",
    )
    make_fake_executable(
        tmp_path / "bad_version",
        "#!/usr/bin/env sh\necho 'not-a-version'\n",
    )
    run_with_fake_path(tmp_path, monkeypatch, [])

    result = doctor.run_diagnostics(
        tmp_path,
        timeout=2,
        evaluators=[
            ("missing", ("missing", "--version")),
            ("bad_exit", ("bad_exit", "--version")),
            ("bad_version", ("bad_version", "--version")),
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


@pytest.mark.parametrize(
    "usable_count, expected_mode, expected_min",
    [
        (0, "blocked", 0),
        (1, "advisory", 1),
        (2, "strict", 2),
    ],
)
def test_recommendation_modes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, usable_count: int, expected_mode: str, expected_min: int) -> None:
    specs: list[tuple[str, tuple[str, ...]]] = []

    for i in range(usable_count):
        evaluator = tmp_path / f"good_{i}"
        make_fake_executable(evaluator, "#!/usr/bin/env sh\necho 'v0.0.1'\n")
        specs.append((f"good_{i}", (f"good_{i}", "--version")))

    while len(specs) < 2:
        bad_name = f"bad_{len(specs)}"
        make_fake_executable(
            tmp_path / bad_name,
            "#!/usr/bin/env sh\necho 'invalid'\n",
        )
        specs.append((bad_name, (bad_name, "--version")))

    if usable_count < 2:
        extras = []
    else:
        extras = []

    run_with_fake_path(tmp_path, monkeypatch, extras)
    result = doctor.run_diagnostics(tmp_path, timeout=2, evaluators=specs)

    assert result["recommendation"]["mode"] == expected_mode
    assert result["recommendation"]["min_models"] == expected_min
    assert len(result["recommendation"]["eval_models"]) == usable_count


def test_doctor_json_schema_includes_setup_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_fake_executable(
        tmp_path / "codex",
        "#!/usr/bin/env sh\nprintf 'codex 0.5.0'\n",
    )
    run_with_fake_path(tmp_path, monkeypatch, [])

    payload = doctor.run_diagnostics(
        tmp_path,
        timeout=1,
        evaluators=[("codex", ("codex", "--version"))],
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
    assert "python scripts/doctor.py --project-root" in content
    assert "recommendation" in content
    assert "Python | 3.12+" in content or "Required: 3.12+" in content


def test_python_requirement_wiring_matches_readme_and_setup_docs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docko = (ROOT / "docs/README.ko.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    setup = (ROOT / "skills/ahoy-setup/SKILL.md").read_text(encoding="utf-8")

    assert "3.12+" in readme
    assert "3.12+" in docko
    assert "3.12" in claude
    assert "3.12+" in setup

