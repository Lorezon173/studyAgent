"""Phase 3a：RedisPubSub 单元测试，使用 fakeredis 避免真实 Redis 依赖。"""
import threading
import time
import pytest
import fakeredis

from app.services.redis_pubsub import RedisPubSub


@pytest.fixture
def pubsub():
    client = fakeredis.FakeRedis(decode_responses=False)
    return RedisPubSub(client)


def test_publish_then_subscribe_roundtrip(pubsub):
    """订阅者先订阅，发布者后发布，订阅方应收到消息序列直至 done。"""
    received: list[tuple[str, str]] = []

    def consumer():
        for event, data in pubsub.subscribe("ch:test1", timeout_s=2.0):
            received.append((event, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()

    time.sleep(0.1)
    pubsub.publish("ch:test1", "accepted", "task-123")
    pubsub.publish("ch:test1", "token", "hello")
    pubsub.publish("ch:test1", "done", "[DONE]")

    t.join(timeout=3.0)
    assert received == [
        ("accepted", "task-123"),
        ("token", "hello"),
        ("done", "[DONE]"),
    ]


def test_subscribe_terminates_on_error_event(pubsub):
    received: list[tuple[str, str]] = []

    def consumer():
        for event, data in pubsub.subscribe("ch:test2", timeout_s=2.0):
            received.append((event, data))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)
    pubsub.publish("ch:test2", "error", "boom")

    t.join(timeout=3.0)
    assert received == [("error", "boom")]


def test_subscribe_raises_timeout_when_no_message(pubsub):
    with pytest.raises(TimeoutError):
        for _ in pubsub.subscribe("ch:silent", timeout_s=0.5):
            pytest.fail("should not yield any message")


def test_channels_are_isolated(pubsub):
    received_a: list[tuple[str, str]] = []
    received_b: list[tuple[str, str]] = []

    def consumer(channel, sink):
        for event, data in pubsub.subscribe(channel, timeout_s=2.0):
            sink.append((event, data))

    ta = threading.Thread(target=consumer, args=("ch:A", received_a), daemon=True)
    tb = threading.Thread(target=consumer, args=("ch:B", received_b), daemon=True)
    ta.start()
    tb.start()
    time.sleep(0.1)
    pubsub.publish("ch:A", "token", "alpha")
    pubsub.publish("ch:A", "done", "[DONE]")
    pubsub.publish("ch:B", "token", "beta")
    pubsub.publish("ch:B", "done", "[DONE]")

    ta.join(timeout=3.0)
    tb.join(timeout=3.0)
    assert received_a == [("token", "alpha"), ("done", "[DONE]")]
    assert received_b == [("token", "beta"), ("done", "[DONE]")]
