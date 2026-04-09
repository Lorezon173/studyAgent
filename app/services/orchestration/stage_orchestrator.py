from app.agent.graph import initial_graph, qa_direct_graph, restate_graph, summary_graph
from app.agent.state import LearningState
from app.services.learning_analysis import persist_learning_outcome


class StageOrchestrator:
    @staticmethod
    def run_initial(state: LearningState) -> LearningState:
        return initial_graph.invoke(state)

    @staticmethod
    def run_restate(state: LearningState) -> LearningState:
        return restate_graph.invoke(state)

    @staticmethod
    def run_summary(state: LearningState) -> LearningState:
        result = summary_graph.invoke(state)
        result = persist_learning_outcome(result)
        result["reply"] = result.get("summary", "")
        return result

    @staticmethod
    def run_qa_direct(state: LearningState) -> LearningState:
        return qa_direct_graph.invoke(state)

    @staticmethod
    def run_by_stage(state: LearningState) -> LearningState:
        current_stage = state.get("stage")
        if current_stage == "explained":
            return StageOrchestrator.run_restate(state)
        if current_stage == "followup_generated":
            return StageOrchestrator.run_summary(state)
        return StageOrchestrator.run_initial(state)

