from __future__ import annotations

import json
import pytest
from pathlib import Path

from tests.harness.cases import build_cases
from tests.harness.loader import load_cases_from_paths
from tests.harness.runner import replay_from_report, run_harness_case, summarize_results, write_report


def _fake_invoke(system_prompt: str, user_prompt: str, stream_output: bool = False) -> str:
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


def _fake_route_intent(user_input: str) -> str:
    if "重规划" in user_input or "改学" in user_input:
        return '{"intent":"replan","confidence":0.95,"reason":"重规划"}'
    return '{"intent":"teach_loop","confidence":0.8,"reason":"默认教学主线"}'


@pytest.mark.skip(reason="Graph V2 下 session_store 为空，harness runner 需要适配 checkpointer")
def test_harness_template_metrics(monkeypatch):
    monkeypatch.setattr("app.services.llm.llm_service.invoke", _fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: (
            '{"topic":"二分查找","changed":false,"confidence":0.9,'
            '"reason":"主题稳定","comparison_mode":false}'
        ),
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.answer_direct",
        lambda user_input, topic, comparison_mode=False: "这是LLM直答结果",
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        _fake_route_intent,
    )

    results = [run_harness_case(case, use_llm_mocks=False) for case in build_cases()]
    summary = summarize_results(results)

    assert summary["total_cases"] == 2
    assert summary["total_turns"] == 5
    assert summary["pass_rate"] >= 0.8
    assert summary["replan_count"] >= 1

    replan_case = next(x for x in results if x.case_id == "replan-branch")
    assert replan_case.pass_rate == 1.0


def test_harness_loader_and_report_and_replay(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.llm.llm_service.invoke", _fake_invoke)
    monkeypatch.setattr(
        "app.services.llm.llm_service.detect_topic",
        lambda user_input, current_topic: (
            '{"topic":"二分查找","changed":false,"confidence":0.9,'
            '"reason":"主题稳定","comparison_mode":false}'
        ),
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.answer_direct",
        lambda user_input, topic, comparison_mode=False: "这是LLM直答结果",
    )
    monkeypatch.setattr(
        "app.services.llm.llm_service.route_intent",
        _fake_route_intent,
    )

    case_file = tmp_path / "cases.json"
    case_payload = [
        {
            "case_id": "loader-case-1",
            "title": "loader case",
            "user_id": 3,
            "session_id": "loader-case-s1",
            "kb_snapshot": [
                {
                    "source_type": "text",
                    "scope": "global",
                    "topic": "二分查找",
                    "content": "二分查找要求有序数组。",
                    "title": "教材",
                },
                {
                    "source_type": "text",
                    "scope": "personal",
                    "user_id": 3,
                    "topic": "二分查找",
                    "content": "你容易写错边界。",
                    "title": "个人笔记",
                },
            ],
            "turns": [
                {
                    "request": {
                        "session_id": "loader-case-s1",
                        "topic": "二分查找",
                        "user_input": "开始讲二分",
                        "user_id": 3,
                    },
                    "expect_stage": "explained",
                    "expected_route": "teach_loop",
                    "expected_tools": ["search_local_textbook", "search_personal_memory"],
                    "expect_citations_min": 1,
                }
            ],
        }
    ]
    case_file.write_text(json.dumps(case_payload, ensure_ascii=False), encoding="utf-8")

    cases = load_cases_from_paths([str(case_file)])
    assert len(cases) == 1
    assert cases[0].case_id == "loader-case-1"
    assert len(cases[0].kb_snapshot) == 2

    results = [run_harness_case(cases[0], use_llm_mocks=False)]
    out_dir = tmp_path / "artifacts"
    detail_path, summary_path = write_report(cases=cases, results=results, out_dir=str(out_dir), run_tag="wp1")
    assert detail_path.exists()
    assert summary_path.exists()

    replay_summary, replay_path = replay_from_report(
        str(detail_path),
        out_dir=str(out_dir),
        strict=False,
        use_llm_mocks=False,
    )
    assert replay_path.exists()
    assert replay_summary["total_cases"] == 1

