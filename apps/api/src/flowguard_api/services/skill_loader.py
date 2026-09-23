from pathlib import Path


class SkillLoadError(RuntimeError):
    pass


def load_skill(skills_dir: str | Path, skill_name: str) -> str:
    """Load one explicitly selected SKILL.md without executing plugin files."""
    skill_file = Path(skills_dir) / skill_name / "SKILL.md"
    try:
        content = skill_file.read_text(encoding="utf-8").lstrip("\ufeff")
    except (OSError, UnicodeError) as error:
        raise SkillLoadError(f"无法读取 Skill：{skill_file}") from error

    instructions = _strip_frontmatter(content).strip()
    if not instructions:
        raise SkillLoadError(f"Skill 内容为空：{skill_file}")
    return instructions


def _strip_frontmatter(content: str) -> str:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return content

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :])
    return content
