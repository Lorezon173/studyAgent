from __future__ import annotations

import json
import shlex
import uuid
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.services.agent_service import agent_service
from app.services.file_extract_service import extract_text_from_upload, infer_source_type_from_filename
from app.services.learning_profile_store import (
    aggregate_by_topic,
    build_session_timeline,
    get_learning_profile,
    get_profile_overview,
)
from app.services.rag_service import rag_service
from app.services.session_store import clear_all_sessions, clear_session, get_session, list_sessions
from app.services.user_store import get_user_store
from app.services.llm import llm_service
from app.skills.builtin import register_builtin_skills
from app.skills.registry import skill_registry

CommandHandler = Callable[[list[str]], None]


@dataclass
class CLIContext:
    user_id: int
    username: str
    session_id: str
    topic: str | None = None
    running: bool = True


class LearningAgentCLI:
    def __init__(self) -> None:
        user = self._require_login()
        self.ctx = CLIContext(
            user_id=int(user["user_id"]),
            username=str(user["username"]),
            session_id=self._new_session_id(),
        )
        self.commands: dict[str, CommandHandler] = {
            "help": self._cmd_help,
            "h": self._cmd_help,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "session": self._cmd_session,
            "topic": self._cmd_topic,
            "skills": self._cmd_skills,
            "profile": self._cmd_profile,
            "chat": self._cmd_chat,
            "status": self._cmd_status,
            "plan": self._cmd_plan,
            "trace": self._cmd_trace,
            "kadd": self._cmd_kadd,
            "ksearch": self._cmd_ksearch,
            "klist": self._cmd_klist,
        }

    def run(self) -> None:
        register_builtin_skills()
        self._print_banner()
        while self.ctx.running:
            try:
                raw = input(f"[{self.ctx.session_id}] > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n已退出。")
                return

            if not raw:
                continue
            if raw.startswith("/"):
                self._dispatch_command(raw[1:])
                continue
            self._send_chat(raw)

    def _dispatch_command(self, raw_command: str) -> None:
        try:
            parts = shlex.split(raw_command)
        except ValueError as err:
            print(f"命令解析失败: {err}")
            return
        if not parts:
            return
        command = parts[0].lower()
        handler = self.commands.get(command)
        if handler is None:
            print(f"未知命令: /{command}，输入 /help 查看可用命令。")
            return
        handler(parts[1:])

    def _cmd_help(self, _: list[str]) -> None:
        print(
            """可用命令:
/help                               显示帮助
/status                             查看当前 CLI 上下文
/session show                       显示当前会话
/session new                        新建会话并切换
/session set <session_id>           切换到指定会话
/session list                       列出所有会话
/session clear [session_id]         清理会话(默认当前)
/session clear-all                  清理全部会话
/topic show                         显示当前主题
/topic set <topic>                  设置当前主题
/topic clear                        清空当前主题
/skills                             列出技能
/skills <name>                      查看技能详情
/profile <session_id>               查看会话聚合档案
/profile overview                   查看总体概览
/profile topic <topic>              查看主题聚合
/profile timeline <session_id>      查看会话时间线
/plan show                          查看当前会话计划
/trace [session_id]                 查看分支决策轨迹
/kadd text <scope> <topic> <title> <content>   入库文本知识（scope: global|personal）
/kadd file <scope> <topic> <file_path> [title] 入库文件（txt/docx/pdf/png/jpg/jpeg）
/ksearch <scope> <query> [top_k] [topic]        检索知识库
/klist                              查看知识库统计
/chat <message>                     发送消息
/exit                               退出 CLI
普通文本输入同样会作为聊天消息发送。"""
        )

    def _cmd_exit(self, _: list[str]) -> None:
        self.ctx.running = False
        print("已退出。")

    def _cmd_status(self, _: list[str]) -> None:
        stage = get_session(self.ctx.session_id)
        stage_name = (stage or {}).get("stage", "start")
        print(
            json.dumps(
                {
                    "user_id": self.ctx.user_id,
                    "username": self.ctx.username,
                    "current_session_id": self.ctx.session_id,
                    "current_topic": self.ctx.topic,
                    "current_stage": stage_name,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def _cmd_session(self, args: list[str]) -> None:
        if not args or args[0] == "show":
            print(f"当前会话: {self.ctx.session_id}")
            return

        sub = args[0]
        if sub == "new":
            self.ctx.session_id = self._new_session_id()
            print(f"已切换到新会话: {self.ctx.session_id}")
            return
        if sub == "set" and len(args) >= 2:
            self.ctx.session_id = args[1]
            print(f"已切换会话: {self.ctx.session_id}")
            return
        if sub == "list":
            sessions = list_sessions()
            rows = []
            for sid, state in sessions.items():
                rows.append(
                    {
                        "session_id": sid,
                        "stage": state.get("stage", "unknown"),
                        "topic": state.get("topic"),
                    }
                )
            print(json.dumps({"total": len(rows), "sessions": rows}, ensure_ascii=False, indent=2))
            return
        if sub == "clear-all":
            clear_all_sessions()
            print("已清理全部会话。")
            return
        if sub == "clear":
            sid = args[1] if len(args) >= 2 else self.ctx.session_id
            clear_session(sid)
            print(f"已清理会话: {sid}")
            return
        print("session 子命令无效，输入 /help 查看用法。")

    def _cmd_topic(self, args: list[str]) -> None:
        if not args or args[0] == "show":
            print(f"当前主题: {self.ctx.topic}")
            return
        if args[0] == "clear":
            self.ctx.topic = None
            print("已清空主题。")
            return
        if args[0] == "set" and len(args) >= 2:
            self.ctx.topic = " ".join(args[1:])
            print(f"已设置主题: {self.ctx.topic}")
            return
        print("topic 子命令无效，输入 /help 查看用法。")

    def _cmd_skills(self, args: list[str]) -> None:
        if not args:
            skills = [{"name": s.name, "description": s.description} for s in skill_registry.list()]
            print(json.dumps({"total": len(skills), "skills": skills}, ensure_ascii=False, indent=2))
            return
        skill = skill_registry.get(args[0])
        if skill is None:
            print(f"未找到技能: {args[0]}")
            return
        print(json.dumps({"name": skill.name, "description": skill.description}, ensure_ascii=False, indent=2))

    def _cmd_profile(self, args: list[str]) -> None:
        if not args:
            print("profile 命令缺少参数，输入 /help 查看用法。")
            return
        sub = args[0]
        if sub == "overview":
            print(json.dumps(get_profile_overview(), ensure_ascii=False, indent=2))
            return
        if sub == "topic" and len(args) >= 2:
            topic = " ".join(args[1:])
            print(json.dumps(aggregate_by_topic(topic, user_id=self.ctx.user_id), ensure_ascii=False, indent=2))
            return
        if sub == "timeline" and len(args) >= 2:
            sid = args[1]
            print(
                json.dumps(
                    {"session_id": sid, "events": build_session_timeline(sid, user_id=self.ctx.user_id)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        sid = sub
        data = get_learning_profile(sid, user_id=self.ctx.user_id)
        if not any(data.values()):
            print(f"未找到学习档案: {sid}")
            return
        print(json.dumps({"session_id": sid, **data}, ensure_ascii=False, indent=2))

    def _cmd_chat(self, args: list[str]) -> None:
        if not args:
            print("chat 命令缺少消息内容。")
            return
        self._send_chat(" ".join(args))

    def _cmd_plan(self, args: list[str]) -> None:
        if not args or args[0] != "show":
            print("用法: /plan show")
            return
        state = get_session(self.ctx.session_id)
        if state is None:
            print("当前会话不存在。")
            return
        print(json.dumps(state.get("current_plan"), ensure_ascii=False, indent=2))

    def _cmd_trace(self, args: list[str]) -> None:
        sid = args[0] if args else self.ctx.session_id
        state = get_session(sid)
        if state is None:
            print(f"会话不存在: {sid}")
            return
        print(
            json.dumps(
                {
                    "session_id": sid,
                    "trace": state.get("branch_trace", []),
                    "topic_segments": state.get("topic_segments", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def _cmd_kadd(self, args: list[str]) -> None:
        if len(args) < 1:
            print("用法: /kadd text <scope> <topic> <title> <content> | /kadd file <scope> <topic> <file_path> [title]")
            return
        mode = args[0].lower()
        if mode == "text":
            if len(args) < 5:
                print("用法: /kadd text <scope> <topic> <title> <content>")
                return
            scope, topic, title = args[1], args[2], args[3]
            content = " ".join(args[4:])
            self._kadd_text(scope=scope, topic=topic, title=title, content=content)
            return
        if mode == "file":
            if len(args) < 4:
                print("用法: /kadd file <scope> <topic> <file_path> [title]")
                return
            scope, topic, file_path = args[1], args[2], args[3]
            title = args[4] if len(args) >= 5 else None
            self._kadd_file(scope=scope, topic=topic, file_path=file_path, title=title)
            return
        print("仅支持 /kadd text 或 /kadd file")

    def _cmd_ksearch(self, args: list[str]) -> None:
        if len(args) < 2:
            print("用法: /ksearch <scope> <query> [top_k] [topic]")
            return
        scope = args[0].lower()
        query = args[1]
        top_k = int(args[2]) if len(args) >= 3 else 3
        topic = args[3] if len(args) >= 4 else self.ctx.topic
        if scope == "personal":
            rows = rag_service.retrieve_scoped(
                query=query,
                scope="personal",
                user_id=str(self.ctx.user_id),
                topic=topic,
                top_k=top_k,
            )
        elif scope == "global":
            rows = rag_service.retrieve(query=query, topic=topic, top_k=top_k)
        else:
            print("scope 仅支持 global|personal")
            return
        view = [
            {
                "score": x.get("score"),
                "scope": x.get("scope", scope),
                "topic": x.get("topic"),
                "title": x.get("title"),
                "snippet": str(x.get("text", ""))[:160],
            }
            for x in rows
        ]
        print(json.dumps({"total": len(view), "items": view}, ensure_ascii=False, indent=2))

    def _cmd_klist(self, args: list[str]) -> None:
        _ = args
        kb_path = Path(settings.rag_store_path)
        personal_path = Path(settings.personal_rag_store_path)

        stats: dict[str, dict[str, int | bool]] = {
            "knowledge_chunks": {
                "exists": kb_path.exists(),
                "lines": 0,
                "global_count": 0,
                "personal_count": 0,
            },
            "personal_rag": {
                "exists": personal_path.exists(),
                "lines": 0,
            },
        }

        if kb_path.exists():
            for line in kb_path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text:
                    continue
                stats["knowledge_chunks"]["lines"] = int(stats["knowledge_chunks"]["lines"]) + 1
                try:
                    obj = json.loads(text)
                    scope = str(obj.get("scope", "global"))
                    if scope == "personal":
                        stats["knowledge_chunks"]["personal_count"] = int(
                            stats["knowledge_chunks"]["personal_count"]
                        ) + 1
                    else:
                        stats["knowledge_chunks"]["global_count"] = int(
                            stats["knowledge_chunks"]["global_count"]
                        ) + 1
                except json.JSONDecodeError:
                    continue

        if personal_path.exists():
            stats["personal_rag"]["lines"] = len(personal_path.read_text(encoding="utf-8").splitlines())

        print(json.dumps(stats, ensure_ascii=False, indent=2))

    def _kadd_text(self, *, scope: str, topic: str, title: str, content: str) -> None:
        if scope not in {"global", "personal"}:
            print(f"错误: scope必须是global或personal，当前: {scope}")
            return
        user_id = str(self.ctx.user_id) if scope == "personal" else None
        try:
            inserted = rag_service.ingest(
                source_type="text",
                scope=scope,
                user_id=user_id,
                content=content,
                topic=topic,
                title=title,
                source_uri=None,
                chapter=None,
                page_no=None,
                image_id=None,
                chunk_size=None,
                chunk_overlap=None,
            )
        except Exception as err:  # noqa: BLE001
            print(f"入库失败: {err}")
            return
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "text",
                    "scope": scope,
                    "topic": topic,
                    "title": title,
                    "inserted": inserted,
                    "content_preview": content[:120],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def _kadd_file(self, *, scope: str, topic: str, file_path: str, title: str | None) -> None:
        if scope not in {"global", "personal"}:
            print(f"错误: scope必须是global或personal，当前: {scope}")
            return
        path = Path(file_path)
        if not path.exists():
            print(f"文件不存在: {path}")
            return
        try:
            payload = path.read_bytes()
            source_type = infer_source_type_from_filename(path.name)
            content = extract_text_from_upload(filename=path.name, payload=payload, source_type=source_type)
            user_id = str(self.ctx.user_id) if scope == "personal" else None
            inserted = rag_service.ingest(
                source_type=source_type,
                scope=scope,
                user_id=user_id,
                content=content,
                topic=topic,
                title=title or path.name,
                source_uri=str(path),
                chapter=None,
                page_no=None,
                image_id=None,
                chunk_size=None,
                chunk_overlap=None,
            )
        except Exception as err:  # noqa: BLE001
            print(f"入库失败: {err}")
            return
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "file",
                    "scope": scope,
                    "topic": topic,
                    "file": str(path),
                    "source_type": source_type,
                    "inserted": inserted,
                    "text_length": len(content),
                    "text_preview": content[:120],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def _send_chat(self, user_input: str) -> None:
        try:
            stream_started = {"value": False}

            def _on_chunk(chunk: str) -> None:
                if not stream_started["value"]:
                    print("\n[streaming] ", end="", flush=True)
                    stream_started["value"] = True
                print(chunk, end="", flush=True)

            with llm_service.stream_to(_on_chunk):
                result = agent_service.run(
                    session_id=self.ctx.session_id,
                    topic=self.ctx.topic,
                    user_input=user_input,
                    user_id=self.ctx.user_id,
                    stream_output=True,
                )
        except Exception as err:  # noqa: BLE001
            print(f"调用失败: {err}")
            return

        stage = result.get("stage", "unknown")
        if stream_started["value"]:
            print("")
            print(f"[stage: {stage}]\n")
            return
        reply = result.get("reply", "")
        print(f"\n[stage: {stage}]\n{reply}\n")

    @staticmethod
    def _new_session_id() -> str:
        return f"cli-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _print_banner() -> None:
        print(
            "Learning Agent CLI 已启动。\n"
            "输入 /help 查看命令；直接输入文本即可聊天。"
        )

    @staticmethod
    def _require_login() -> dict:
        store = get_user_store()
        while True:
            print("\n=== 登录入口 ===")
            print("1) 登录")
            print("2) 注册")
            choice = input("请选择 [1/2]: ").strip()
            if choice == "2":
                username = input("请输入用户名: ").strip()
                password = getpass("请输入密码: ")
                try:
                    user = store.create_user(username=username, password=password)
                    print(f"注册成功：username={user['username']}，user_id={user['user_id']}")
                except ValueError as err:
                    print(f"注册失败: {err}")
                    continue
            elif choice != "1":
                print("无效选择，请输入 1 或 2。")
                continue

            users = store.list_users()
            print("\n当前已注册用户：")
            for row in users:
                print(f"- user_id={row['user_id']}, username={row['username']}")

            username = input("请输入用户名登录: ").strip()
            password = getpass("请输入密码: ")
            try:
                user = store.authenticate(username=username, password=password)
                print(f"登录成功：{user['username']} (user_id={user['user_id']})")
                return user
            except ValueError as err:
                print(f"登录失败: {err}")


def main() -> None:
    LearningAgentCLI().run()


def choose_user_for_cli() -> dict:
    return LearningAgentCLI._require_login()
