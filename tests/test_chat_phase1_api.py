from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_response_contains_evidence_meta(monkeypatch):
    monkeypatch.setattr(
        "app.api.chat.agent_service.run",
        lambda **kwargs: {
            "session_id": "s-evidence",
            "stage": "rag_answered",
            "reply": "回答",
            "summary": None,
            "citations": [],
            "rag_confidence_level": "medium",
            "rag_low_evidence": False,
        },
    )
    resp = client.post("/chat", json={"session_id": "s-evidence", "user_input": "二分查找是什么"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rag_confidence_level"] == "medium"
    assert data["rag_low_evidence"] is False
