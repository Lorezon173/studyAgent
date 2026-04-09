from app.agent.state import LearningState
from app.services.session_store import save_session


class PersistenceCoordinator:
    @staticmethod
    def save_state(session_id: str, state: LearningState) -> None:
        save_session(session_id, state)

