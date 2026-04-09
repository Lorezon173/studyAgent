from app.skills.base import BaseSkill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        name = getattr(skill, "name", "").strip()
        if not name:
            raise ValueError("Skill 缺少 name，无法注册。")
        if name in self._skills:
            raise ValueError(f"Skill 已存在：{name}")
        self._skills[name] = skill

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list(self) -> list[BaseSkill]:
        return list(self._skills.values())


skill_registry = SkillRegistry()
