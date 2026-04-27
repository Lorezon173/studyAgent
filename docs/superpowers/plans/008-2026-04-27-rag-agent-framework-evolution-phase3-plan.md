# Phase 3 - RAG Agent Framework Evolution (Plan & Delivery Record)

Date: 2026-04-27
Branch: `worktree-phase3-wireup`

This document records the Phase 3 wireup work and known carry-over items.

---

## 已知遗留（Phase 4 待办）

- **`route_on_error` 未接入 `graph_v2.py`**：函数与单元测试已交付（commit `26f90f1`），`error_code` 写入也已交付（commit `23c4249`），但图中无 `add_conditional_edges` 引用该路由。原因：接入需将固定边 `knowledge_retrieval -> explain` 改为条件边，会影响 teach_loop 主流程。本期 Task 0 范围决策保留 teach_loop 不变。Phase 4 节点装饰器/状态分层任务中一并处理。
- **E2E 测试 mock 较多**：`test_phase3_e2e.py` 三个用例均 mock 了 `llm_service.invoke` / `route_intent` / `execute_retrieval_tools`。验证的是图接线、节点路径、元数据传播；不验证真实 LLM/检索行为。集成测试（不带 mock）见 Phase 4 计划。
- **`nodes.py` 已 696 行**：Phase 4 计划拆分为 `nodes/teach.py` / `nodes/qa.py` / `nodes/orchestration.py`。
