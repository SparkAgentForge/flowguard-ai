from pathlib import Path

import pytest

from flowguard_api.infrastructure.ai.providers import Step5InferenceAdapter
from flowguard_api.services.skill_loader import SkillLoadError, load_skill


def write_skill(root: Path, content: str) -> Path:
    skill_file = root / "assembly-video-audit" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


def test_load_skill_strips_frontmatter(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "---\nname: assembly-video-audit\ndescription: test\n---\n\n# 审核规则\n\n只看画面。\n",
    )

    instructions = load_skill(tmp_path, "assembly-video-audit")

    assert instructions == "# 审核规则\n\n只看画面。"
    assert "description:" not in instructions


def test_load_skill_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="无法读取 Skill"):
        load_skill(tmp_path, "assembly-video-audit")


def test_step5_adapter_reloads_skill_for_each_prompt(tmp_path: Path, monkeypatch) -> None:
    skill_file = write_skill(tmp_path, "第一版规则")
    adapter = Step5InferenceAdapter()
    monkeypatch.setattr(adapter.settings, "skills_dir", str(tmp_path))

    first_prompt = adapter._chat_payload([], [])["messages"][0]["content"]
    assert first_prompt.startswith("第一版规则\n\n")
    assert "start_seconds 和 end_seconds 必须填 null" in first_prompt

    skill_file.write_text("第二版规则", encoding="utf-8")

    second_prompt = adapter._chat_payload([], [])["messages"][0]["content"]
    assert second_prompt.startswith("第二版规则\n\n")
    assert "第一版规则" not in second_prompt
    assert "start_seconds 和 end_seconds 必须填 null" in second_prompt
