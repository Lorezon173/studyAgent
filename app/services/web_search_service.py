from typing import Protocol

from app.core.config import settings


class WebSearchProvider(Protocol):
    def search(self, query: str, top_k: int) -> list[dict]:
        ...


class StubWebSearchProvider:
    """默认占位实现：返回空结果，便于本地与离线环境运行。"""

    def search(self, query: str, top_k: int) -> list[dict]:
        return []


class MockWebSearchProvider:
    """测试/演示用实现：根据 query 生成可追踪的伪结果。"""

    def search(self, query: str, top_k: int) -> list[dict]:
        if not query.strip():
            return []
        k = max(1, int(top_k))
        rows: list[dict] = []
        for idx in range(1, k + 1):
            rows.append(
                {
                    "chunk_id": f"web-{idx}",
                    "source_type": "web",
                    "scope": "global",
                    "title": f"Web结果 {idx}",
                    "source_uri": f"https://example.com/search?q={query}&p={idx}",
                    "text": f"[web] 与“{query}”相关的第{idx}条检索结果（mock provider）。",
                    "score": max(0.0, 1.0 - (idx - 1) * 0.1),
                }
            )
        return rows


class WebSearchService:
    def __init__(self) -> None:
        provider_name = (settings.web_search_provider or "stub").strip().lower()
        if provider_name == "mock":
            self.provider: WebSearchProvider = MockWebSearchProvider()
        else:
            self.provider = StubWebSearchProvider()

    def search(self, query: str, top_k: int) -> list[dict]:
        return self.provider.search(query=query, top_k=top_k)


web_search_service = WebSearchService()

