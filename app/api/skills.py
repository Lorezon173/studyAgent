from fastapi import APIRouter, HTTPException

from app.models.schemas import SkillListResponse, SkillResponse
from app.skills.registry import skill_registry

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillListResponse)
def list_skills() -> SkillListResponse:
    items = [SkillResponse(name=s.name, description=s.description) for s in skill_registry.list()]
    return SkillListResponse(skills=items, total=len(items))


@router.get("/{skill_name}", response_model=SkillResponse)
def get_skill(skill_name: str) -> SkillResponse:
    skill = skill_registry.get(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"未找到技能：{skill_name}")
    return SkillResponse(name=skill.name, description=skill.description)
