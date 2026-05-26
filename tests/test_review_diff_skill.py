from __future__ import annotations

from pathlib import Path


def test_review_diff_skill_entrypoint_exists_and_documents_required_modes():
    skill = Path("skills/ahoy-review-diff/SKILL.md")

    assert skill.exists()
    content = skill.read_text(encoding="utf-8")
    assert "name: ahoy:review-diff" in content
    assert "scripts/review_diff.py" in content
    assert "advisory" in content
    assert "strict" in content
    assert ".claude/harness/sprints" in content
    assert "do not" in content.lower()
