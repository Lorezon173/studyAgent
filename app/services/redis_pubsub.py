"""Redis Pub/Sub 极简封装，供 Phase 3 异步链路在 web 与 worker 进程间桥接事件。"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Iterator, Protocol

import redis

from app.core.config import settings

_TERMINAL_EVENTS = ("done", "error")


class _RedisLike(Protocol):
    def publish(self, channel: str, message: bytes | str) -> int: ...
    def pubsub(self): ...


class RedisPubSub:
    """对 redis-py 的薄封装，统一 `(event, data)` 字符串协议与终止语义。"""

    def __init__(self, client: _RedisLike) -> None:
        self._client = client

    def publish(self, channel: str, event: str, data: str) -> None:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        self._client.publish(channel, payload)

    def subscribe(self, channel: str, timeout_s: float = 30.0) -> Iterator[tuple[str, str]]:
        """订阅频道，逐条 yield (event, data)。

        注意：这是 generator，第一次 next() 才会真正 ps.subscribe()。
        若需要"返回前订阅就绪"的语义，请使用 open_subscription 上下文。
        """
        ps = self._client.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(channel)
        try:
            yield from self._iter_until_terminal(ps, channel, timeout_s)
        finally:
            try:
                ps.unsubscribe(channel)
                ps.close()
            except Exception:
                pass

    @contextmanager
    def open_subscription(self, channel: str, timeout_s: float = 30.0):
        """同步上下文：进入即订阅，退出自动关闭。

        与 subscribe() 不同，open_subscription 在 with 块进入时立即 ps.subscribe()，
        因此在 with 块内部发布的消息一定能被收到，避免"早发布漏收"的时序问题。
        """
        ps = self._client.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(channel)
        try:
            yield self._iter_until_terminal(ps, channel, timeout_s)
        finally:
            try:
                ps.unsubscribe(channel)
                ps.close()
            except Exception:
                pass

    def _iter_until_terminal(self, ps, channel: str, timeout_s: float) -> Iterator[tuple[str, str]]:
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"pubsub timeout on channel={channel}")
            msg = ps.get_message(timeout=min(remaining, 0.1))
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            raw = msg.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            event = str(payload.get("event", ""))
            data = str(payload.get("data", ""))
            yield event, data
            if event in _TERMINAL_EVENTS:
                return


def get_default_pubsub() -> RedisPubSub:
    """从全局 settings 构造默认实例。生产路径使用。"""
    client = redis.from_url(settings.redis_url)
    return RedisPubSub(client)
