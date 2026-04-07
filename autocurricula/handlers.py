from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from .engine import chat_with_claude, name_workspace
from .intellisense import get_completions, get_hover, get_signatures
from .models import ProblemMeta, ProblemStatus
from .session import Session
from .workspace import create_workspace


class _HandlersProto(Protocol):
    session: Session | None
    current_problem: ProblemMeta | None
    current_problem_dir: Path | None
    _chat_busy: bool
    _chat_queue: list[dict]

    async def send(self, msg: dict) -> None: ...
    async def send_log(self, html: str, style: str = ...) -> None: ...
    async def set_busy(self, busy: bool) -> None: ...
    def _problem_payload(self, meta: ProblemMeta, d: Path) -> dict: ...
    async def _send_app_state(self) -> None: ...
    async def _send_landing(self) -> None: ...
    async def _generate_next(self) -> None: ...
    async def _process_chat_queue(self) -> None: ...
    async def _cmd_run(self) -> None: ...
    async def _cmd_test(self) -> None: ...
    async def _cmd_submit(self) -> None: ...
    async def _cmd_scaffold(self) -> None: ...
    async def _cmd_give_up(self) -> None: ...
    async def _cmd_show(self) -> None: ...
    async def _cmd_problems(self) -> None: ...
    async def _cmd_progress(self) -> None: ...
    async def _cmd_replay(self, args: list[str]) -> None: ...
    async def _cmd_resume(self) -> None: ...


class HandlersMixin:
    """WebSocket message handlers, mixed into SessionHandler."""

    session: Session | None
    current_problem: ProblemMeta | None
    current_problem_dir: Path | None

    async def _handle_select_workspace(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        slug = data.get("slug", "").strip()
        if not slug:
            return
        from .server import _safe_workspace_path
        ws_dir = _safe_workspace_path(slug)
        if ws_dir is None:
            await self.send({"type": "error", "message": "Invalid workspace"})
            return
        role_file = ws_dir / ".role"
        if not role_file.exists():
            await self.send({"type": "error", "message": "Workspace not found"})
            return
        role = role_file.read_text().strip()
        from .workspace import CONFIG_FILE
        CONFIG_FILE.write_text(slug)
        session = Session(role, ws_dir)
        self.session = session
        await self._send_app_state()
        current = session.get_current()
        if current is None or current.status != ProblemStatus.IN_PROGRESS:
            await self._generate_next()

    async def _handle_load_problem(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        slug = data.get("slug", "").strip()
        problem_id = data.get("problem_id", "").strip()
        if not slug or not problem_id:
            return
        from .server import _safe_workspace_path
        ws_dir = _safe_workspace_path(slug)
        if ws_dir is None:
            return
        role_file = ws_dir / ".role"
        if not role_file.exists():
            return
        role = role_file.read_text().strip()
        from .workspace import CONFIG_FILE
        CONFIG_FILE.write_text(slug)
        self.session = Session(role, ws_dir)
        d = self.session._problem_dir(problem_id)
        if not d.resolve().is_relative_to(ws_dir.resolve()):
            return
        meta = self.session._load_problem_from_dir(d)
        if meta:
            state = self.session._load_state()
            state.current_problem_id = problem_id
            state.problems[problem_id] = meta
            self.session._save_state(state)
            self.current_problem = meta
            self.current_problem_dir = d
            payload = self._problem_payload(meta, d)
            await self.send({
                "type": "state",
                "needs_onboarding": False,
                "role": self.session.role,
                "problem": payload,
            })
        else:
            await self._send_app_state()

    async def _handle_clear_problem(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        slug = data.get("slug", "").strip()
        problem_id = data.get("problem_id", "").strip()
        if not slug or not problem_id:
            return
        from .server import _safe_workspace_path
        ws_dir = _safe_workspace_path(slug)
        if ws_dir is None:
            return
        role_file = ws_dir / ".role"
        if not role_file.exists():
            return
        role = role_file.read_text().strip()
        session = Session(role, ws_dir)
        d = session._problem_dir(problem_id)
        if not d.resolve().is_relative_to(ws_dir.resolve()):
            return
        meta, problem_dir = session.replay_problem(problem_id)
        if meta:
            await self._send_landing()

    async def _handle_create_workspace(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        user_input = data.get("role", "").strip()
        if not user_input:
            return
        await self.set_busy(True)
        try:
            role = await asyncio.to_thread(name_workspace, user_input)
            _, workspace_dir = await asyncio.to_thread(create_workspace, role, user_input)
            self.session = Session(role, workspace_dir)
            await self._send_app_state()
            await self._generate_next()
        except Exception as e:
            await self.set_busy(False)
            await self.send({"type": "error", "message": str(e)})

    async def _handle_onboard(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        user_input = data.get("role", "").strip()
        if not user_input:
            return
        await self.set_busy(True)
        await self.send_log('<span class="dim">Setting up workspace...</span>')
        try:
            role = await asyncio.to_thread(name_workspace, user_input)
            _, workspace_dir = await asyncio.to_thread(create_workspace, role, user_input)
            self.session = Session(role, workspace_dir)
            await self.send({"type": "onboarded", "role": role})
            await self.send_log(f'<span class="c-success">Workspace: <span class="bold">{role}</span></span>')
            await self._generate_next()
        except Exception as e:
            await self.set_busy(False)
            await self.send_log(f'<span class="c-error">Error: {e}</span>')

    async def _handle_next_problem(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        has_parent = data.get("has_parent", False)
        if has_parent and self.session is not None:
            problem = self.session.get_current()
            if problem and problem.parent_problem:
                parent, parent_dir = self.session.resume_parent()
                if parent and parent_dir:
                    self.current_problem = parent
                    self.current_problem_dir = parent_dir
                    payload = self._problem_payload(parent, parent_dir)
                    await self.send({"type": "problem_loaded", "problem": payload})
                    return
        await self._generate_next()

    async def _handle_rate_problem(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        problem_id = data.get("problem_id")
        rating = data.get("rating")
        if not problem_id or not isinstance(rating, int) or rating < 1 or rating > 5:
            return
        if self.session is None:
            return
        await asyncio.to_thread(self.session.rate_problem, problem_id, rating)

    async def _handle_go_home(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        self.session = None
        self.current_problem = None
        self.current_problem_dir = None
        await self._send_landing()

    async def _handle_chat(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        message = data.get("message", "").strip()
        if not message:
            return
        self._chat_queue.append(data)
        if self._chat_busy:
            return
        await self._process_chat_queue()

    async def _process_chat_queue(self: _HandlersProto) -> None:  # type: ignore[misc]
        self._chat_busy = True
        await self.send({"type": "chat_busy", "busy": True})
        while self._chat_queue:
            data = self._chat_queue.pop(0)
            message = data.get("message", "").strip()
            if not message:
                continue

            question = None
            is_markdown = bool(self.current_problem and self.current_problem.format == "markdown")

            editor_code = data.get("code")
            if self.current_problem_dir:
                q_path = self.current_problem_dir / "question.md"
                if q_path.exists():
                    question = q_path.read_text()
                sol_file = "solution.md" if is_markdown else "solution.py"
                if editor_code is not None:
                    (self.current_problem_dir / sol_file).write_text(editor_code)
                sol_path = self.current_problem_dir / sol_file
                user_code = sol_path.read_text() if sol_path.exists() else None
            else:
                user_code = editor_code

            chat_history = []
            if self.session and self.current_problem:
                chat_history = self.session.load_chat(self.current_problem.id)
                self.session.append_chat(self.current_problem.id, "user", message)

            try:
                response = await asyncio.to_thread(
                    chat_with_claude, message, question, user_code, is_markdown, chat_history
                )
                await self.send({"type": "chat_response", "text": response})
                if self.session and self.current_problem:
                    self.session.append_chat(self.current_problem.id, "assistant", response)
            except Exception as e:
                await self.send({"type": "chat_response", "html": f'<span class="c-error">error: {e}</span>'})
        self._chat_busy = False
        await self.send({"type": "chat_busy", "busy": False})

    async def _handle_command(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        name = data.get("name", "").lower()
        args = data.get("args", [])
        code = data.get("code")
        if code is not None and self.current_problem_dir and self.current_problem_dir.exists():
            if self.current_problem and self.current_problem.format == "markdown":
                (self.current_problem_dir / "solution.md").write_text(code)
            else:
                (self.current_problem_dir / "solution.py").write_text(code)
        handler = {
            "run": self._cmd_run,
            "test": self._cmd_test,
            "submit": self._cmd_submit,
            "scaffold": self._cmd_scaffold,
            "give-up": self._cmd_give_up,
            "giveup": self._cmd_give_up,
            "skip": self._cmd_give_up,
            "show": self._cmd_show,
            "problems": self._cmd_problems,
            "progress": self._cmd_progress,
            "replay": lambda: self._cmd_replay(args),
            "resume": self._cmd_resume,
        }.get(name)
        if handler:
            await handler()
        else:
            await self.send_log(f'<span class="c-error">unknown command: /{name}</span>')

    async def _handle_code_sync(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        code = data.get("code", "")
        if self.current_problem_dir and self.current_problem_dir.exists():
            if self.current_problem and self.current_problem.format == "markdown":
                (self.current_problem_dir / "solution.md").write_text(code)
            else:
                (self.current_problem_dir / "solution.py").write_text(code)

    async def _handle_completions(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        req_id = data.get("id", "")
        source = data.get("source", "")
        line = data.get("line", 1)
        column = data.get("column", 1)
        try:
            items = await asyncio.to_thread(get_completions, source, line, column)
        except Exception:
            items = []
        await self.send({"type": "completions_result", "id": req_id, "items": items})

    async def _handle_hover(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        req_id = data.get("id", "")
        source = data.get("source", "")
        line = data.get("line", 1)
        column = data.get("column", 1)
        try:
            result = await asyncio.to_thread(get_hover, source, line, column)
        except Exception:
            result = None
        await self.send({"type": "hover_result", "id": req_id, "content": result})

    async def _handle_signatures(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        req_id = data.get("id", "")
        source = data.get("source", "")
        line = data.get("line", 1)
        column = data.get("column", 1)
        try:
            result = await asyncio.to_thread(get_signatures, source, line, column)
        except Exception:
            result = []
        await self.send({"type": "signatures_result", "id": req_id, "signatures": result})

    async def _handle_confirm_response(self: _HandlersProto, data: dict) -> None:  # type: ignore[misc]
        pass
