"""Phase 7 Task 1: Retry Policy Single Source of Truth 一致性测试。

守住三个数据源的同步：
- `app.agent.retry_policy.RETRY_POLICIES_MAP`（运行时字典 SSOT）
- `app.agent.node_decorator.RetryKey` Literal（IDE/mypy 静态检查）
- `app.agent.node_decorator._VALID_RETRY_KEYS`（运行时校验集合，应派生自 MAP）

任何一处加新 retry_key 而忘记同步另一处，CI 立刻挂。
"""
from typing import get_args

import pytest

from app.agent.node_decorator import RetryKey, _VALID_RETRY_KEYS, node
from app.agent.retry_policy import RETRY_POLICIES_MAP


def test_valid_retry_keys_derived_from_map():
    """运行时校验集合必须等于 MAP 的 keys。"""
    assert set(_VALID_RETRY_KEYS) == set(RETRY_POLICIES_MAP.keys())


def test_literal_matches_map_keys():
    """Literal 字面量必须与 MAP keys 一致。

    PEP 586 不允许 Literal 从动态值派生，所以这里只能手工同步并测试守卫。
    """
    literal_values = set(get_args(RetryKey))
    assert literal_values == set(RETRY_POLICIES_MAP.keys()), (
        f"RetryKey Literal {literal_values} out of sync with "
        f"RETRY_POLICIES_MAP {set(RETRY_POLICIES_MAP.keys())}. "
        "Update both in lockstep."
    )


def test_invalid_retry_key_rejected_at_decoration_time():
    """未知 retry 字符串在 @node 入口立即抛错。"""
    with pytest.raises(ValueError, match="retry"):
        @node(name="bad_retry_node_ssot", retry="UNKNOWN_RETRY")  # type: ignore[arg-type]
        def _bad(state):
            return state


def test_graph_v2_uses_map_directly():
    """graph_v2 应该直接传入 RETRY_POLICIES_MAP 而非重新构造字典。"""
    import app.agent.graph_v2 as g
    assert g.RETRY_POLICIES_MAP is RETRY_POLICIES_MAP, (
        "graph_v2 must import RETRY_POLICIES_MAP from retry_policy, not redefine"
    )


@pytest.mark.parametrize("retry_key", list(RETRY_POLICIES_MAP.keys()))
def test_each_map_key_accepted_by_decorator(retry_key):
    """MAP 中每个 key 都应被装饰器接受（防止 MAP 引入了 Literal 没声明的 key）。"""
    @node(name=f"ssot_accepts_{retry_key.lower()}", retry=retry_key)
    def n(state):
        return state
    from app.agent.node_decorator import get_node_meta
    assert get_node_meta(n).retry_key == retry_key
