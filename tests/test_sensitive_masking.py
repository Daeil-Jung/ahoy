"""Tests for SensitiveDataMasker and its integration with collect_code_snippets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import load_module

eval_dispatch = load_module("test_masking_module", "scripts/eval_dispatch.py")


def test_masker_detects_api_key():
    masker = eval_dispatch.SensitiveDataMasker()
    code = 'api_key = "sk-abc123456789012345678901"'
    result = masker.mask(code)
    assert "sk-abc123456789012345678901" not in result
    assert "[MASKED_API_KEY_1]" in result
    assert masker.masked_count == 1


def test_masker_detects_password():
    masker = eval_dispatch.SensitiveDataMasker()
    code = 'password: "hunter2secret"'
    result = masker.mask(code)
    assert "hunter2secret" not in result
    assert "[MASKED_PASSWORD_1]" in result


def test_masker_detects_connection_string():
    masker = eval_dispatch.SensitiveDataMasker()
    code = 'db_url = "mongodb://admin:pass@host:27017/db"'
    result = masker.mask(code)
    assert "mongodb://admin:pass@host:27017/db" not in result
    assert "[MASKED_CONN_STRING_1]" in result


def test_masker_detects_bearer_token():
    masker = eval_dispatch.SensitiveDataMasker()
    code = 'headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.test1234"}'
    result = masker.mask(code)
    assert "eyJhbGciOiJIUzI1NiJ9.test1234" not in result
    assert "[MASKED_BEARER_1]" in result


def test_masker_detects_aws_key():
    masker = eval_dispatch.SensitiveDataMasker()
    code = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
    result = masker.mask(code)
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "[MASKED_AWS_KEY_1]" in result


def test_masker_detects_private_key():
    masker = eval_dispatch.SensitiveDataMasker()
    code = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowI...\n-----END RSA PRIVATE KEY-----"
    result = masker.mask(code)
    assert "BEGIN RSA PRIVATE KEY" not in result
    assert "[MASKED_PRIVATE_KEY_1]" in result


def test_masker_preserves_line_count():
    masker = eval_dispatch.SensitiveDataMasker()
    code = 'line1\napi_key = "sk-abc123456789012345678901"\nline3\n'
    result = masker.mask(code)
    assert code.count("\n") == result.count("\n")


def test_masker_no_false_positive_on_normal_code():
    masker = eval_dispatch.SensitiveDataMasker()
    code = "api_key_count = 5\npassword_length = 12\ntoken_valid = True\n"
    result = masker.mask(code)
    assert result == code
    assert masker.masked_count == 0


def test_masker_same_literal_reuses_token():
    masker = eval_dispatch.SensitiveDataMasker()
    code = 'api_key = "sk-abc123456789012345678901"\napi_key = "sk-abc123456789012345678901"'
    result = masker.mask(code)
    assert result.count("[MASKED_API_KEY_1]") == 2
    assert masker.masked_count == 1


def test_masker_different_literals_get_unique_tokens():
    masker = eval_dispatch.SensitiveDataMasker()
    code = (
        'api_key = "sk-first_key_abcdef01234567"\n'
        'api_token = "sk-second_key_abcdef0123456"\n'
    )
    result = masker.mask(code)
    assert "[MASKED_API_KEY_1]" in result
    assert "[MASKED_API_KEY_2]" in result
    assert masker.masked_count == 2


def test_masker_custom_pattern_from_config():
    masker = eval_dispatch.SensitiveDataMasker(extra_patterns=[
        {"category": "CUSTOM", "mask_prefix": "MASKED_CUSTOM", "regex": r"XPREFIX-[A-Z0-9]{10}"},
    ])
    code = 'value = "XPREFIX-ABCDEFGH12"'
    result = masker.mask(code)
    assert "XPREFIX-ABCDEFGH12" not in result
    assert "[MASKED_CUSTOM_1]" in result


def test_masker_disabled_in_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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
    file_path.write_text('api_key = "sk-abc123456789012345678901"\n', encoding="utf-8")

    def fake_call_model(model: str, prompt: str, timeout: int = 600) -> str:
        assert "sk-abc123456789012345678901" in prompt
        return json.dumps({
            "verdict": "pass", "issues": [],
            "passed_criteria": ["AC-001"], "failed_criteria": [],
            "summary": "pass",
        })

    monkeypatch.setattr(eval_dispatch, "call_model", fake_call_model)
    monkeypatch.setattr(
        eval_dispatch, "load_config",
        lambda: {
            "eval_models": ["codex", "claude"], "min_models": 2,
            "cost_limit": None,
            "sensitive_data_masking": {"enabled": False},
        },
    )
    monkeypatch.setattr(
        eval_dispatch.sys, "argv",
        ["eval_dispatch.py", str(sprint_dir), "--models", "codex,claude",
         "--project-root", str(project_root)],
    )
    assert eval_dispatch.main() == 0


def test_collect_code_snippets_with_masker(tmp_path: Path):
    sprint_dir = tmp_path / "sprint-001"
    sprint_dir.mkdir()
    (sprint_dir / "gen_report.md").write_text(
        "### Files Modified\n- `scripts/example.py`\n",
        encoding="utf-8",
    )
    project_root = tmp_path / "project"
    file_path = project_root / "scripts" / "example.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        'db = "postgres://user:pass@localhost/mydb"\nprint("hello")\n',
        encoding="utf-8",
    )

    masker = eval_dispatch.SensitiveDataMasker()
    snippets = eval_dispatch.collect_code_snippets(sprint_dir, project_root, masker=masker)

    assert "postgres://user:pass@localhost/mydb" not in snippets
    assert "[MASKED_CONN_STRING_1]" in snippets
    assert 'print("hello")' in snippets
    assert masker.masked_count == 1
