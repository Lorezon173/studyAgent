from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import chainlit as cl
from chainlit.chat_settings import ChatSettings
from chainlit.input_widget import Select, TextInput

from app.core.config import settings
from app.ui.chainlit_backend import BackendApiError, BackendClient


def _backend() -> BackendClient:
    return BackendClient(base_url=settings.backend_base_url, timeout=60.0)


def _session_id() -> str:
    sid = cl.user_session.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    new_sid = f"web-{uuid.uuid4().hex[:10]}"
    cl.user_session.set("session_id", new_sid)
    return new_sid


def _user_id() -> int | None:
    uid = cl.user_session.get("user_id")
    return uid if isinstance(uid, int) else None


def _topic() -> str | None:
    topic = cl.user_session.get("topic")
    return topic if isinstance(topic, str) and topic else None


def _session_label(session: dict[str, Any]) -> str:
    sid = str(session.get("session_id", ""))
    topic = str(session.get("topic") or "未命名主题")
    stage = str(session.get("stage") or "unknown")
    return f"{topic} [{stage}] ({sid})"


async def _sync_sidebar_settings() -> None:
    client = _backend()
    current_sid = _session_id()
    items: dict[str, str] = {}

    try:
        sessions = client.list_sessions().get("sessions", [])
    except BackendApiError:
        sessions = []

    for s in sessions:
        if isinstance(s, dict) and s.get("session_id"):
            items[_session_label(s)] = str(s["session_id"])

    if current_sid not in items.values():
        synthetic = {"session_id": current_sid, "topic": _topic(), "stage": "active"}
        items[_session_label(synthetic)] = current_sid

    await ChatSettings(
        inputs=[
            Select(
                id="active_session_id",
                label="会话列表（按主题命名）",
                items=items or {"当前会话": current_sid},
                initial_value=current_sid,
            ),
            TextInput(
                id="active_topic",
                label="当前主题",
                initial=_topic() or "",
                placeholder="输入主题并保存",
            ),
        ]
    ).send()


@cl.password_auth_callback
async def auth_callback(username: str, password: str) -> cl.User | None:
    try:
        body = _backend().login(username, password)
    except BackendApiError:
        return None
    user_id = body.get("user_id")
    if not isinstance(user_id, int):
        return None
    return cl.User(
        identifier=username,
        display_name=str(body.get("username", username)),
        metadata={"user_id": user_id},
    )


@cl.on_chat_start
async def on_chat_start() -> None:
    if not isinstance(cl.user_session.get("session_id"), str):
        cl.user_session.set("session_id", f"web-{uuid.uuid4().hex[:10]}")

    user = cl.user_session.get("user")
    if isinstance(user, cl.User):
        uid = user.metadata.get("user_id")
        if isinstance(uid, int):
            cl.user_session.set("user_id", uid)

    await _sync_sidebar_settings()
    await cl.Message(
        content=(
            "学习助手已启动。\n"
            "请通过右上角登录按钮完成登录。\n"
            "可用命令：`/newsession`、`/use <session_id>`、`/topic`、`/skills`、`/sessions`、`/profile`、`/memory`、`/kadd`、`/ksearch`、`/reset`、`/resetall`"
        )
    ).send()


@cl.on_settings_update
async def on_settings_update(settings_map: dict[str, Any]) -> None:
    selected_sid = settings_map.get("active_session_id")
    if isinstance(selected_sid, str) and selected_sid:
        cl.user_session.set("session_id", selected_sid)
        try:
            sessions = _backend().list_sessions().get("sessions", [])
            for s in sessions:
                if isinstance(s, dict) and s.get("session_id") == selected_sid:
                    topic = s.get("topic")
                    if isinstance(topic, str) and topic:
                        cl.user_session.set("topic", topic)
                    break
        except BackendApiError:
            pass

    edited_topic = settings_map.get("active_topic")
    if isinstance(edited_topic, str):
        topic = edited_topic.strip()
        if topic:
            cl.user_session.set("topic", topic)


@cl.on_message
async def on_message(message: cl.Message) -> None:
    text = (message.content or "").strip()
    if not text:
        await cl.Message(content="请输入内容。").send()
        return

    if text.startswith("/"):
        await _handle_command(text)
        return

    uid = _user_id()
    if uid is None:
        await cl.Message(content="请先通过右上角登录按钮完成登录。").send()
        return

    client = _backend()
    msg = cl.Message(content="")
    await msg.send()

    sid = _session_id()
    topic = _topic()
    streamed = False

    try:
        for event, data in client.chat_stream(session_id=sid, user_input=text, user_id=uid, topic=topic):
            if event == "token":
                streamed = True
                await msg.stream_token(data.replace("\\n", "\n"))
            elif event == "stage":
                await cl.Message(content=f"阶段：`{data}`").send()
            elif event == "error":
                raise BackendApiError(data)
            elif event == "done":
                break

        if streamed:
            await msg.update()
            return

        fallback = client.chat(session_id=sid, user_input=text, user_id=uid, topic=topic)
        msg.content = str(fallback.get("reply", ""))
        await msg.update()
        await _sync_sidebar_settings()
    except BackendApiError as exc:
        await cl.Message(content=f"请求失败：{exc}").send()


async def _handle_command(text: str) -> None:
    client = _backend()
    parts = text.split()
    cmd = parts[0].lower()

    try:
        if cmd in {"/register", "/login"}:
            await cl.Message(content="请使用右上角登录按钮，避免在聊天框明文输入账号密码。").send()
            return

        if cmd == "/topic":
            if len(parts) < 2:
                current = _topic() or "未设置"
                await cl.Message(content=f"当前主题：`{current}`。设置方式：`/topic 主题名`").send()
                return
            topic = " ".join(parts[1:]).strip()
            cl.user_session.set("topic", topic)
            await cl.Message(content=f"主题已设置为：`{topic}`").send()
            await _sync_sidebar_settings()
            return

        if cmd == "/skills":
            body = client.list_skills()
            skills = body.get("skills", [])
            lines = [f"- `{x.get('name')}`: {x.get('description', '')}" for x in skills]
            await cl.Message(content="技能列表：\n" + ("\n".join(lines) if lines else "无")).send()
            return

        if cmd == "/sessions":
            body = client.list_sessions()
            sessions = body.get("sessions", [])
            lines = [f"- `{s.get('session_id')}` stage={s.get('stage')}" for s in sessions]
            await cl.Message(content="会话列表：\n" + ("\n".join(lines) if lines else "无")).send()
            return

        if cmd == "/newsession":
            cl.user_session.set("session_id", f"web-{uuid.uuid4().hex[:10]}")
            await cl.Message(content="已创建新会话并切换。").send()
            await _sync_sidebar_settings()
            return

        if cmd == "/use":
            if len(parts) < 2:
                await cl.Message(content="用法：`/use <session_id>`").send()
                return
            selected_sid = parts[1].strip()
            body = client.list_sessions()
            sessions = body.get("sessions", [])
            exists = any(
                isinstance(s, dict) and str(s.get("session_id")) == selected_sid for s in sessions
            )
            if not exists:
                await cl.Message(content=f"未找到会话：`{selected_sid}`").send()
                return

            cl.user_session.set("session_id", selected_sid)
            for s in sessions:
                if isinstance(s, dict) and s.get("session_id") == selected_sid:
                    topic = s.get("topic")
                    if isinstance(topic, str) and topic:
                        cl.user_session.set("topic", topic)
                    break
            await cl.Message(content=f"已切换会话：`{selected_sid}`").send()
            await _sync_sidebar_settings()
            return

        if cmd == "/profile":
            sid = _session_id()
            body = client.get_profile(sid, _user_id())
            pretty = json.dumps(body, ensure_ascii=False, indent=2)
            await cl.Message(content=f"当前会话画像：\n```json\n{pretty}\n```").send()
            return

        if cmd == "/memory":
            topic = _topic()
            if not topic:
                await cl.Message(content="请先设置主题：`/topic 主题名`").send()
                return
            body = client.get_topic_memory(topic, _user_id())
            pretty = json.dumps(body, ensure_ascii=False, indent=2)
            await cl.Message(content=f"主题长期记忆：\n```json\n{pretty}\n```").send()
            return

        if cmd == "/kadd":
            if len(parts) < 2:
                await cl.Message(content="用法：`/kadd 要入库的文本内容`").send()
                return
            content = text[len("/kadd") :].strip()
            body = client.knowledge_ingest(
                source_type="text",
                content=content,
                topic=_topic(),
                scope="personal" if _user_id() is not None else "global",
                user_id=_user_id(),
                title="chainlit-manual-input",
            )
            await cl.Message(content=f"知识入库成功：`inserted={body.get('inserted')}`").send()
            return

        if cmd == "/ksearch":
            if len(parts) < 2:
                await cl.Message(content="用法：`/ksearch 查询词`").send()
                return
            query = text[len("/ksearch") :].strip()
            body = client.knowledge_retrieve(
                query=query,
                topic=_topic(),
                scope="personal" if _user_id() is not None else "global",
                user_id=_user_id(),
                top_k=5,
            )
            items: list[dict[str, Any]] = body.get("items", [])
            lines = [f"- ({i+1}) score={it.get('score')}: {it.get('text', '')[:120]}" for i, it in enumerate(items)]
            await cl.Message(content="知识检索结果：\n" + ("\n".join(lines) if lines else "无结果")).send()
            return

        if cmd == "/reset":
            sid = _session_id()
            client.clear_session(sid)
            cl.user_session.set("session_id", f"web-{uuid.uuid4().hex[:10]}")
            await cl.Message(content=f"已清理会话：`{sid}`，并创建新会话。").send()
            await _sync_sidebar_settings()
            return

        if cmd == "/resetall":
            client.clear_all_sessions()
            cl.user_session.set("session_id", f"web-{uuid.uuid4().hex[:10]}")
            await cl.Message(content="已清理全部会话，并创建当前新会话。").send()
            await _sync_sidebar_settings()
            return

        await cl.Message(content="未知命令。可用：`/login` `/register` `/newsession` `/use` `/topic` `/skills` `/sessions` `/profile` `/memory` `/kadd` `/ksearch` `/reset` `/resetall`").send()
    except BackendApiError as exc:
        await cl.Message(content=f"命令执行失败：{exc}").send()
