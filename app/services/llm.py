from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import time

from app.core.config import settings
from app.monitoring import trace_llm


class LLMService:
    def __init__(self) -> None:
        self.llm: ChatOpenAI | None = None
        self._stream_consumer: ContextVar[Callable[[str], None] | None] = ContextVar(
            "llm_stream_consumer",
            default=None,
        )

    def _get_llm(self) -> ChatOpenAI:
        if self.llm is None:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY 未配置，无法调用模型。")
            self.llm = ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                base_url=settings.openai_base_url,
                temperature=0.3,
                timeout=settings.llm_timeout_seconds,
            )
        return self.llm

    def _chunk_to_text(self, content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return ""

    @contextmanager
    def stream_to(self, consumer: Callable[[str], None] | None) -> Iterator[None]:
        token = self._stream_consumer.set(consumer)
        try:
            yield
        finally:
            self._stream_consumer.reset(token)

    @trace_llm("invoke")
    def invoke(self, system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        max_retries = max(0, int(settings.llm_max_retries))
        backoff = float(settings.llm_retry_backoff_seconds)
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                consumer = self._stream_consumer.get()
                if stream_output and consumer is not None:
                    chunks: list[str] = []
                    for chunk in self._get_llm().stream(messages):
                        piece = self._chunk_to_text(chunk.content)
                        if not piece:
                            continue
                        chunks.append(piece)
                        consumer(piece)
                    return "".join(chunks)
                response = self._get_llm().invoke(messages)
                return response.content if isinstance(response.content, str) else str(response.content)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= max_retries:
                    break
                if backoff > 0:
                    time.sleep(backoff * (2**attempt))
        raise RuntimeError(f"LLM 调用失败（重试后仍失败）: {last_exc}") from last_exc

    def route_intent(self, user_input: str) -> str:
        routing_system = (
            "你是一个路由器，只输出 JSON，不要输出其他内容。"
            "可选 intent: teach_loop, qa_direct, review, replan。"
        )
        routing_user = (
            "根据用户输入判断 intent，并返回 JSON: "
            '{"intent":"...","confidence":0.0-1.0,"reason":"..."}。\n'
            f"用户输入: {user_input}"
        )
        raw = self.invoke(routing_system, routing_user)
        return raw

    def detect_topic(self, user_input: str, current_topic: str | None) -> str:
        topic_system = (
            "你是学习主题识别器，只输出 JSON，不要输出其他内容。"
            "你需要判断用户当前学习主题，并识别是否发生主题切换。"
        )
        topic_user = (
            "请基于输入识别学习主题，并返回 JSON: "
            '{"topic":"字符串或null","changed":true/false,"confidence":0.0-1.0,'
            '"reason":"简短原因","comparison_mode":true/false}。\n'
            f"当前主题: {current_topic or 'null'}\n"
            f"用户输入: {user_input}"
        )
        raw = self.invoke(topic_system, topic_user)
        return raw

    def answer_direct(
        self,
        user_input: str,
        topic: str | None,
        comparison_mode: bool = False,
        stream_output: bool = False,
    ) -> str:
        qa_system = (
            "你是学习问答助手。"
            "请直接、准确、结构化回答用户问题。"
            "如果用户要求比较相近主题，先围绕当前主题作答，再补充必要对比，避免跑题。"
        )
        qa_user = (
            f"当前学习主题: {topic or '未指定'}\n"
            f"是否对比模式: {comparison_mode}\n"
            f"用户问题: {user_input}\n"
            "请给出简洁但完整的回答，并在末尾给出1条可操作建议。"
        )
        return self.invoke(qa_system, qa_user, stream_output=stream_output)


llm_service = LLMService()
