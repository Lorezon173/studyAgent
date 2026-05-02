"""Phase 7 Task 3: truncate_payload 递归截断工具测试。"""
from app.monitoring.desensitize import truncate_payload, truncate_text


# ----- 顶层情形 -----

def test_short_string_unchanged():
    assert truncate_payload("hello") == "hello"


def test_long_string_truncated():
    long = "a" * 2000
    out = truncate_payload(long, max_length=100)
    assert len(out) <= 100 + len("...[truncated]")
    assert out.endswith("...[truncated]")


def test_non_string_scalar_passthrough():
    assert truncate_payload(42) == 42
    assert truncate_payload(3.14) == 3.14
    assert truncate_payload(True) is True
    assert truncate_payload(None) is None


# ----- dict / list 递归 -----

def test_dict_with_long_string_truncated():
    payload = {"name": "ok", "body": "x" * 5000}
    out = truncate_payload(payload, max_length=100)
    assert out["name"] == "ok"
    assert len(out["body"]) <= 100 + len("...[truncated]")


def test_list_of_strings_truncated():
    payload = ["short", "y" * 3000]
    out = truncate_payload(payload, max_length=50)
    assert out[0] == "short"
    assert out[1].endswith("...[truncated]")


def test_nested_dict_recursively_truncated():
    payload = {
        "outer": {
            "inner": {
                "value": "z" * 4000,
            }
        }
    }
    out = truncate_payload(payload, max_length=100)
    assert out["outer"]["inner"]["value"].endswith("...[truncated]")


def test_list_of_dicts_recursively_truncated():
    payload = [{"text": "a" * 2000} for _ in range(3)]
    out = truncate_payload(payload, max_length=80)
    for item in out:
        assert item["text"].endswith("...[truncated]")


# ----- 深度防爆 -----

def test_excessive_depth_falls_back_to_str():
    """深度 > 3 时整体转 str 后截断，避免无限递归 / 巨大笛卡尔展开。"""
    deep = {"a": {"b": {"c": {"d": {"e": "value" * 1000}}}}}
    out = truncate_payload(deep, max_length=200)
    # 顶层 3 层应被正常 dict 化
    assert isinstance(out, dict)
    assert isinstance(out["a"], dict)
    assert isinstance(out["a"]["b"], dict)
    # 第 4 层 (d) 包含的 dict 在 _depth=4 时整体被 str 化
    leaf = out["a"]["b"]["c"]["d"]
    assert isinstance(leaf, str)


# ----- 边界 -----

def test_empty_dict_passthrough():
    assert truncate_payload({}) == {}


def test_empty_list_passthrough():
    assert truncate_payload([]) == []


def test_empty_string_passthrough():
    # truncate_text 对空字符串返回 ""
    assert truncate_payload("") == ""


def test_default_max_length_is_1500():
    """合约：默认 max_length = 1500（覆盖大多数 LLM 单段返回）。"""
    payload = "x" * 1600
    out = truncate_payload(payload)  # 用默认值
    # 1500 + suffix
    assert len(out) <= 1500 + len("...[truncated]")
    assert out.endswith("...[truncated]")


# ----- 与 truncate_text 行为一致 -----

def test_string_truncation_matches_truncate_text():
    s = "hello world " * 200
    assert truncate_payload(s, max_length=80) == truncate_text(s, max_length=80)
