from app.skills.base import BaseSkill
from app.skills.registry import skill_registry
from app.services.personal_rag_store import retrieve_unified_personal_memory
from app.services.rag_service import rag_service
from app.services.web_search_service import web_search_service


class ExplainTermSkill(BaseSkill):
    name = "explain_term"
    description = "解释术语或概念（基础示例技能）"

    def run(self, **kwargs):
        term = kwargs.get("term", "")
        return {"term": term, "result": f"这是对术语 '{term}' 的示例解释。"}


class GenerateQuizSkill(BaseSkill):
    name = "generate_quiz"
    description = "根据主题生成简要测验题（基础示例技能）"

    def run(self, **kwargs):
        topic = kwargs.get("topic", "")
        return {
            "topic": topic,
            "questions": [f"{topic} 的核心概念是什么？", f"{topic} 的典型应用场景是什么？"],
        }


class RetrieveKnowledgeSkill(BaseSkill):
    name = "retrieve_knowledge"
    description = "检索知识库片段（统一文本与OCR文本）"

    def run(self, **kwargs):
        query = str(kwargs.get("query", "")).strip()
        topic = kwargs.get("topic")
        top_k = int(kwargs.get("top_k", 3))
        if not query:
            return {"items": [], "total": 0}
        items = rag_service.retrieve(query=query, topic=topic, top_k=top_k)
        return {"items": items, "total": len(items)}


class SearchLocalTextbookSkill(BaseSkill):
    name = "search_local_textbook"
    description = "检索本地教材/全局知识轨道（global）"

    def run(self, **kwargs):
        query = str(kwargs.get("query", "")).strip()
        topic = kwargs.get("topic")
        top_k = int(kwargs.get("top_k", 3))
        if not query:
            return {"items": [], "total": 0, "scope": "global"}
        items = rag_service.retrieve(query=query, topic=topic, top_k=top_k)
        return {"items": items, "total": len(items), "scope": "global"}


class SearchPersonalMemorySkill(BaseSkill):
    name = "search_personal_memory"
    description = "检索用户私域记忆（personal）- 统一检索"

    def run(self, **kwargs):
        query = str(kwargs.get("query", "")).strip()
        topic = kwargs.get("topic")
        top_k = int(kwargs.get("top_k", 3))
        user_id = kwargs.get("user_id")
        if isinstance(user_id, str) and user_id.isdigit():
            user_id = int(user_id)
        if not query or user_id is None:
            return {"items": [], "total": 0, "scope": "personal"}
        items = retrieve_unified_personal_memory(
            topic=topic or "",
            query=query,
            user_id=int(user_id),
            limit=top_k,
        )
        return {
            "items": items,
            "total": len(items),
            "scope": "personal",
        }


class SearchWebSkill(BaseSkill):
    name = "search_web"
    description = "检索外部网页信息（可插拔 provider）"

    def run(self, **kwargs):
        query = str(kwargs.get("query", "")).strip()
        top_k = int(kwargs.get("top_k", 3))
        if not query:
            return {"items": [], "total": 0, "scope": "global"}
        items = web_search_service.search(query=query, top_k=top_k)
        return {"items": items, "total": len(items), "scope": "global"}


def register_builtin_skills() -> None:
    """注册内置技能（重复调用安全）。"""
    for skill in [
        ExplainTermSkill(),
        GenerateQuizSkill(),
        RetrieveKnowledgeSkill(),
        SearchLocalTextbookSkill(),
        SearchPersonalMemorySkill(),
        SearchWebSkill(),
    ]:
        if skill_registry.get(skill.name) is None:
            skill_registry.register(skill)
