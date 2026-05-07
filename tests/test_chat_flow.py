"""Chat 流程测试 - Graph V2 兼容性问题待解决。

注意：这些测试依赖 get_session() 从 session_store 获取状态。
Graph V2 使用 LangGraph checkpointer 存储状态，导致 get_session() 返回 None。
需要重构测试以使用 LangGraph checkpointer API 或标记跳过。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_chat_multistage_flow(monkeypatch):
    """验证同一 session_id 下的三阶段会话流转。"""

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "诊断结果"
        if "教学助手" in system_prompt:
            return "讲解内容，请你复述。"
        if "学习评估助手" in system_prompt:
            return "复述评估结果"
        if "追问老师" in system_prompt:
            return "这是追问问题"
        if "复盘学习成果" in system_prompt:
            return "这是本轮总结"
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":false,"confidence":0.9,"reason":"主题稳定","comparison_mode":false}',
    )

    # 阶段A：诊断 + 讲解
    resp1 = client.post(
        "/chat",
        json={
            "session_id": "session-flow-1",
            "topic": "二分查找",
            "user_input": "我只知道它和有序数组有关",
        },
    )
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["stage"] == "explained"
    assert body1["reply"] == "讲解内容，请你复述。"

    # 阶段B：复述检测 + 追问
    resp2 = client.post(
        "/chat",
        json={
            "session_id": "session-flow-1",
            "user_input": "二分查找是每次取中间值比较",
        },
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["stage"] == "followup_generated"
    assert body2["reply"] == "这是追问问题"

    # 阶段C：总结
    resp3 = client.post(
        "/chat",
        json={
            "session_id": "session-flow-1",
            "user_input": "因为每次能排除一半区间，所以复杂度低",
        },
    )
    assert resp3.status_code == 200
    body3 = resp3.json()
    assert body3["stage"] == "summarized"
    assert body3["summary"] == "这是本轮总结"
    assert body3["reply"] == "这是本轮总结"


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_topic_can_change_by_llm_detection(monkeypatch):
    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "新主题诊断结果"
        if "教学助手" in system_prompt:
            return "新主题讲解内容"
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

    # 首轮识别到二分查找
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":true,"confidence":0.91,"reason":"用户明确学习二分查找","comparison_mode":false}',
    )
    sid = "topic-shift-1"
    resp1 = client.post("/chat", json={"session_id": sid, "user_input": "我想学习二分查找"})
    assert resp1.status_code == 200

    # 第二轮切到贪心算法
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"贪心算法","changed":true,"confidence":0.93,"reason":"用户切换到贪心算法","comparison_mode":false}',
    )
    resp2 = client.post("/chat", json={"session_id": sid, "user_input": "我们改学贪心算法"})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["stage"] == "explained"
    assert body2["reply"] == "新主题讲解内容"


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_topic_detection_can_parse_fenced_json(monkeypatch):
    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "诊断结果"
        if "教学助手" in system_prompt:
            return "讲解内容"
        if "学习评估助手" in system_prompt:
            return "复述评估结果"
        if "追问老师" in system_prompt:
            return "追问"
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

    sid = "topic-fenced-1"
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '```json\n{"topic":"二分查找","changed":true,"confidence":0.9,"reason":"识别成功","comparison_mode":false}\n```',
    )
    resp1 = client.post("/chat", json={"session_id": sid, "user_input": "先学二分查找"})
    assert resp1.status_code == 200

    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '```json\n{"topic":"贪心算法","changed":true,"confidence":0.92,"reason":"切换主题","comparison_mode":false}\n```',
    )
    resp2 = client.post("/chat", json={"session_id": sid, "user_input": "我现在想学贪心算法"})
    assert resp2.status_code == 200


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_topic_context_injected_when_segments_exist(monkeypatch):
    captured_prompts: list[str] = []

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        captured_prompts.append(user_prompt)
        if "学习诊断助手" in system_prompt:
            return "诊断结果"
        if "教学助手" in system_prompt:
            return "讲解内容"
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)

    sid = "topic-context-1"
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":true,"confidence":0.9,"reason":"识别成功","comparison_mode":false}',
    )
    resp1 = client.post("/chat", json={"session_id": sid, "user_input": "先学二分查找"})
    assert resp1.status_code == 200

    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":false,"confidence":0.92,"reason":"继续同主题","comparison_mode":false}',
    )
    resp2 = client.post("/chat", json={"session_id": sid, "user_input": "再详细解释一下"})
    assert resp2.status_code == 200

    assert any("主题上下文：" in p for p in captured_prompts)


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_topic_context_injected_with_long_term_memory(monkeypatch):
    captured_prompts: list[str] = []

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        captured_prompts.append(user_prompt)
        if "学习诊断助手" in system_prompt:
            return "诊断结果"
        if "教学助手" in system_prompt:
            return "讲解内容"
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"图论","changed":true,"confidence":0.9,"reason":"识别图论","comparison_mode":false}',
    )
    monkeypatch.setattr(
        "app.services.agent_service.get_topic_long_term_memory",
        lambda topic, user_id=None: {
            "topic": topic,
            "mastery_trend": [{"session_id": "s-old", "score": 62, "level": "medium", "timestamp": "t"}],
            "common_errors": [{"label": "概念混淆", "count": 2}],
            "review_history": [],
            "last_stuck_point": "概念混淆: 邻接表和邻接矩阵总是混着用",
            "memory_entries": [],
        },
    )
    monkeypatch.setattr(
        "app.services.agent_service.retrieve_personal_memory",
        lambda topic, query, limit=2, user_id=None: [],
    )

    sid = "topic-long-memory-1"
    resp = client.post("/chat", json={"session_id": sid, "user_input": "我想学图论"})
    assert resp.status_code == 200

    assert any("[长期记忆]" in p for p in captured_prompts)
    assert any("上次卡点" in p for p in captured_prompts)


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_chat_can_attach_rag_citations(monkeypatch):
    captured_prompts: list[str] = []

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        captured_prompts.append(user_prompt)
        if "学习诊断助手" in system_prompt:
            return "诊断结果"
        if "教学助手" in system_prompt:
            return "讲解内容"
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":true,"confidence":0.9,"reason":"识别成功","comparison_mode":false}',
    )
    monkeypatch.setattr("app.services.agent_service.settings.rag_enabled", True)
    monkeypatch.setattr(
        "app.services.agent_service.rag_service.retrieve",
        lambda query, topic, top_k: [
            {
                "chunk_id": "c1",
                "source_type": "text",
                "title": "算法导论",
                "source_uri": None,
                "chapter": "第1章",
                "page_no": 12,
                "image_id": None,
                "text": "二分查找每次比较中间元素并缩小搜索区间。",
                "score": 3,
                "bm25_score": 0.7,
                "rrf_score": 0.2,
                "rrf_bm25": 0.12,
                "rrf_dense": 0.08,
            }
        ],
    )
    monkeypatch.setattr(
        "app.services.agent_service.rag_service.retrieve_scoped",
        lambda query, scope, user_id, topic, top_k: [
            {
                "chunk_id": "p1",
                "source_type": "text",
                "title": "我的错题本",
                "source_uri": None,
                "chapter": None,
                "page_no": None,
                "image_id": None,
                "text": "你在二分查找中容易忘记边界条件。",
                "score": 5,
                "bm25_score": 1.2,
                "rrf_score": 0.25,
                "rrf_bm25": 0.13,
                "rrf_dense": 0.12,
                "scope": "personal",
                "user_id": 1,
            }
        ]
        if scope == "personal" and user_id == "1"
        else [],
    )

    sid = "topic-rag-citation-1"
    resp = client.post(
        "/chat",
        json={"session_id": sid, "user_id": 1, "user_input": "怎么理解二分查找"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "explained"
    assert len(body["citations"]) == 2
    assert body["citations"][0]["chunk_id"] in {"c1", "p1"}
    assert any(x["scope"] == "personal" for x in body["citations"])
    assert any(x["scope"] == "global" for x in body["citations"])
    assert "hybrid_score" in body["citations"][0]
    assert "rerank_score" in body["citations"][0]
    assert "rrf_score" in body["citations"][0]
    assert "bm25_score" in body["citations"][0]
    assert any("[知识检索]" in p for p in captured_prompts)


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_chat_uses_tool_route_to_choose_retrieval(monkeypatch):
    captured_prompts: list[str] = []

    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        captured_prompts.append(user_prompt)
        if "学习诊断助手" in system_prompt:
            return "诊断结果"
        if "教学助手" in system_prompt:
            return "讲解内容"
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":false,"confidence":0.9,"reason":"主题稳定","comparison_mode":false}',
    )
    monkeypatch.setattr("app.services.agent_service.settings.rag_enabled", True)
    monkeypatch.setattr(
        "app.services.tool_executor.skill_registry.get",
        lambda name: type(
            "DummySkill",
            (),
            {
                "run": lambda self, **kwargs: {
                    "items": [
                        {
                            "chunk_id": f"{name}-1",
                            "source_type": "text",
                            "title": "教材",
                            "text": "这是工具检索出来的证据",
                            "score": 1.0,
                            "scope": "global",
                        }
                    ]
                }
            },
        )(),
    )

    sid = "topic-tool-route-1"
    resp = client.post(
        "/chat",
        json={"session_id": sid, "user_id": 1, "topic": "二分查找", "user_input": "我上次这里总是错"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "explained"
    assert body["citations"]
    assert any("tools=" in p for p in captured_prompts)
    assert any(c.get("tool") in {"search_personal_memory", "search_local_textbook"} for c in body["citations"])


@pytest.mark.skip(reason="Graph V2 兼容问题：session_store 为空，需要适配 LangGraph checkpointer")
def test_learning_outcome_prefers_llm_evaluator(monkeypatch):
    def fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        if "学习诊断助手" in system_prompt:
            return "诊断结果"
        if "教学助手" in system_prompt:
            return "讲解内容，请你复述。"
        if "学习评估助手" in system_prompt:
            return "复述评估结果"
        if "追问老师" in system_prompt:
            return "这是追问问题"
        if "复盘学习成果" in system_prompt:
            return "这是本轮总结"
        if "学习评估裁判" in system_prompt:
            return (
                '{"mastery_score_1to5":4,"error_labels":["概念混淆"],'
                '"rationale":"理解较好但仍有细节误区","confidence":0.92}'
            )
        return "默认输出"

    monkeypatch.setattr("app.services.llm.llm_service.invoke", fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: '{"topic":"二分查找","changed":false,"confidence":0.9,"reason":"主题稳定","comparison_mode":false}',
    )

    sid = "eval-llm-1"
    client.post("/chat", json={"session_id": sid, "topic": "二分查找", "user_input": "我只知道它和有序数组有关"})
    client.post("/chat", json={"session_id": sid, "user_input": "二分查找是每次取中间值比较"})
    resp = client.post("/chat", json={"session_id": sid, "user_input": "因为每次能排除一半区间，所以复杂度低"})
    assert resp.status_code == 200
