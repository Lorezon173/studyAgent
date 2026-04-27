from app.agent.routers import route_on_error


def test_route_no_error_goes_to_answer_policy():
    state = {}
    assert route_on_error(state) == "answer_policy"


def test_route_rag_failure_goes_to_recovery():
    state = {"node_error": "rag failed", "error_code": "rag_failure"}
    assert route_on_error(state) == "recovery"


def test_route_llm_timeout_goes_to_retry_then_recovery():
    state = {"node_error": "timed out", "error_code": "llm_timeout", "retry_trace": []}
    assert route_on_error(state) == "retry_rag"


def test_route_llm_timeout_after_retry_goes_to_recovery():
    state = {
        "node_error": "timed out",
        "error_code": "llm_timeout",
        "retry_trace": [{"attempt": 1}],
    }
    assert route_on_error(state) == "recovery"


def test_route_unknown_error_falls_back_to_recovery():
    state = {"node_error": "boom", "error_code": "unknown"}
    assert route_on_error(state) == "recovery"
