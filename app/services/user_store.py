from __future__ import annotations

import hashlib
import hmac
import sqlite3
from pathlib import Path

from app.core.config import settings


def _hash_password(password: str) -> str:
    # Local CLI scenario: deterministic hash with app salt.
    salt = settings.auth_password_salt.encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex()


class UserStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
        self._seed_default_user()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=3000;")
        return conn

    def _init_tables(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    def _seed_default_user(self) -> None:
        if self.get_user_by_username("admin_test") is not None:
            return
        self.create_user(username="admin_test", password="admin")

    def create_user(self, *, username: str, password: str) -> dict:
        clean_name = username.strip()
        if not clean_name:
            raise ValueError("username 不能为空")
        if len(password) < 3:
            raise ValueError("password 长度至少为3")
        pwd_hash = _hash_password(password)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO users(username, password_hash) VALUES (?, ?)",
                    (clean_name, pwd_hash),
                )
                conn.commit()
                uid = int(cur.lastrowid)
            return {"user_id": uid, "username": clean_name}
        except sqlite3.IntegrityError as exc:
            raise ValueError("username 已存在") from exc

    def list_users(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, username FROM users ORDER BY id ASC").fetchall()
        return [{"user_id": int(r["id"]), "username": str(r["username"])} for r in rows]

    def get_user_by_username(self, username: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
        if row is None:
            return None
        return {
            "user_id": int(row["id"]),
            "username": str(row["username"]),
            "password_hash": str(row["password_hash"]),
        }

    def authenticate(self, *, username: str, password: str) -> dict:
        user = self.get_user_by_username(username)
        if user is None:
            raise ValueError("用户名或密码错误")
        actual = user["password_hash"]
        expected = _hash_password(password)
        if not hmac.compare_digest(actual, expected):
            raise ValueError("用户名或密码错误")
        return {"user_id": int(user["user_id"]), "username": str(user["username"])}


_STORE: UserStore | None = None


def get_user_store() -> UserStore:
    global _STORE
    if _STORE is None:
        _STORE = UserStore(settings.user_db_path)
    return _STORE

