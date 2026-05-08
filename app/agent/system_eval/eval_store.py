"""评估结果 SQLite 存储。"""
import json
import sqlite3
from datetime import datetime, UTC


class EvalResultStore:
    """评估结果持久化存储。"""

    def __init__(self, db_path: str = "data/eval_results.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库表。"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eval_results (
                session_id TEXT PRIMARY KEY,
                teaching_eval TEXT NOT NULL,
                orchestrator_eval TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def save(self, session_id: str, teaching_eval: dict, orchestrator_eval: dict):
        """保存评估结果（INSERT OR REPLACE）。"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO eval_results
            (session_id, teaching_eval, orchestrator_eval, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            session_id,
            json.dumps(teaching_eval, ensure_ascii=False),
            json.dumps(orchestrator_eval, ensure_ascii=False),
            datetime.now(UTC).isoformat(),
        ))
        conn.commit()
        conn.close()

    def get(self, session_id: str) -> dict | None:
        """获取指定会话的评估结果。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT session_id, teaching_eval, orchestrator_eval, created_at FROM eval_results WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "session_id": row[0],
            "teaching_eval": json.loads(row[1]),
            "orchestrator_eval": json.loads(row[2]),
            "created_at": row[3],
        }

    def get_stats(self) -> dict:
        """获取评估统计信息。"""
        conn = sqlite3.connect(self.db_path)

        total = conn.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0]

        if total == 0:
            conn.close()
            return {
                "total_evaluations": 0,
                "avg_teaching_score": 0.0,
                "avg_orchestrator_score": 0.0,
            }

        avg_teaching = conn.execute(
            "SELECT AVG(json_extract(teaching_eval, '$.teaching_score')) FROM eval_results"
        ).fetchone()[0]

        avg_orchestrator = conn.execute(
            "SELECT AVG(json_extract(orchestrator_eval, '$.orchestrator_score')) FROM eval_results"
        ).fetchone()[0]

        conn.close()

        return {
            "total_evaluations": total,
            "avg_teaching_score": round(avg_teaching or 0.0, 2),
            "avg_orchestrator_score": round(avg_orchestrator or 0.0, 2),
        }
