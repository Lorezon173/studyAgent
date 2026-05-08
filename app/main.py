from fastapi import FastAPI

from app.core.config import settings
from app.api.chat import router as chat_router
from app.api.chat_multi import router as multi_chat_router
from app.api.sessions import router as sessions_router
from app.api.skills import router as skills_router
from app.api.profile import router as profile_router
from app.api.knowledge import router as knowledge_router
from app.api.auth import router as auth_router
from app.skills.builtin import register_builtin_skills

app = FastAPI(title=settings.app_name, debug=settings.debug)

register_builtin_skills()

app.include_router(chat_router)
app.include_router(multi_chat_router)
app.include_router(sessions_router)
app.include_router(skills_router)
app.include_router(profile_router)
app.include_router(knowledge_router)
app.include_router(auth_router)


@app.get("/health")
def health():
    """健康检查端点"""
    return {"status": "ok", "app": settings.app_name}
