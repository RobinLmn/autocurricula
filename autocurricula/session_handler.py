from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from .commands import CommandsMixin
from .engine import GenerationProgress, get_usage_last_24h
from .handlers import HandlersMixin
from .models import ProblemMeta, ProblemStatus
from .progress import load_progress
from .session import Session
from .workspace import WORKSPACES_DIR, get_progress_file, init_workspace, list_workspaces


class SessionHandler(HandlersMixin, CommandsMixin):
    """Manages a single WebSocket connection and its associated Session."""

    def __init__(self, ws: WebSocket, role: str | None = None):
        self.ws = ws
        self.session: Session | None = None
        self.current_problem: ProblemMeta | None = None
        self.current_problem_dir: Path | None = None
        self._busy = False
        self._cmd_lock = asyncio.Lock()
        self._confirm_future: asyncio.Future[bool] | None = None
        self._chat_busy = False
        self._chat_queue: list[dict] = []
        self._initial_role = role
        self._pooled_problem: tuple[ProblemMeta, Path] | None = None
        self._pool_task: asyncio.Task | None = None
        self._generate_cancelled = False
        self._generate_task: asyncio.Task | None = None

    async def send(self, msg: dict) -> None:
        try:
            await self.ws.send_json(msg)
        except Exception:
            pass

    async def send_log(self, html: str, style: str = "") -> None:
        await self.send({"type": "log", "html": html, "style": style})

    async def set_busy(self, busy: bool) -> None:
        self._busy = busy
        await self.send({"type": "busy", "busy": busy})

    async def run(self) -> None:
        if self._initial_role:
            result = init_workspace(self._initial_role)
            if result is not None:
                role, workspace_dir = result
                self.session = Session(role, workspace_dir)
                await self._send_app_state()
            else:
                await self._send_landing()
        else:
            await self._send_landing()
        try:
            while True:
                data = await self.ws.receive_json()
                msg_type = data.get("type", "")
                handler = getattr(self, f"_handle_{msg_type}", None)
                if handler:
                    await handler(data)
        except WebSocketDisconnect:
            pass

    def _get_workspaces_data(self) -> list[dict]:
        workspaces = list_workspaces()
        result = []
        for slug, role in workspaces.items():
            ws_dir = WORKSPACES_DIR / slug
            pf = get_progress_file(ws_dir)
            state = load_progress(pf)
            problems = list(state.problems.values())
            solved = sum(1 for p in problems if p.status == ProblemStatus.SOLVED)
            failed = sum(1 for p in problems if p.status == ProblemStatus.FAILED)
            in_prog = sum(1 for p in problems if p.status == ProblemStatus.IN_PROGRESS)
            total = len(problems)
            by_cat: dict[str, dict] = {}
            by_tag: dict[str, int] = {}
            for p in problems:
                cat = p.category
                if cat not in by_cat:
                    by_cat[cat] = {"solved": 0, "total": 0}
                by_cat[cat]["total"] += 1
                if p.status == ProblemStatus.SOLVED:
                    by_cat[cat]["solved"] += 1
                for tag in p.tags:
                    by_tag[tag] = by_tag.get(tag, 0) + 1
            history = sorted(problems, key=lambda p: p.created_at, reverse=True)
            history_items = [
                {
                    "id": p.id,
                    "title": p.title,
                    "category": p.category,
                    "difficulty": p.difficulty.value,
                    "format": p.format,
                    "status": p.status.value,
                    "attempts": p.attempts,
                    "tags": p.tags,
                }
                for p in history
            ]
            result.append(
                {
                    "slug": slug,
                    "role": role,
                    "total": total,
                    "solved": solved,
                    "failed": failed,
                    "in_progress": in_prog,
                    "rate": round((solved / total * 100), 1) if total else 0,
                    "categories": by_cat,
                    "tags": by_tag,
                    "history": history_items,
                }
            )
        return result

    @staticmethod
    def _check_claude_cli() -> str | None:
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return "Claude CLI found but returned an error. Reinstall it from https://claude.ai/download"
            return None
        except FileNotFoundError:
            return "Claude CLI not found. Install it from https://claude.ai/download"
        except Exception as e:
            return f"Could not verify Claude CLI: {e}"

    async def _send_landing(self) -> None:
        claude_error = self._check_claude_cli()
        await self.send(
            {
                "type": "landing",
                "workspaces": self._get_workspaces_data(),
                "usage_24h": get_usage_last_24h(),
                **({"claude_error": claude_error} if claude_error else {}),
            }
        )

    async def _send_app_state(self) -> None:
        assert self.session is not None
        problem = self.session.get_current()
        state_msg: dict = {
            "type": "state",
            "needs_onboarding": False,
            "role": self.session.role,
        }
        if problem and problem.status == ProblemStatus.IN_PROGRESS:
            d = self.session._problem_dir(problem.id)
            self.current_problem = problem
            self.current_problem_dir = d
            state_msg["problem"] = self._problem_payload(problem, d)
            self._start_pool()
        await self.send(state_msg)

    @staticmethod
    def _extract_test_names(filepath: Path) -> list[str]:
        names = []
        if filepath.exists():
            for line in filepath.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("def test_"):
                    name = stripped.split("(", 1)[0].replace("def ", "")
                    names.append(name)
        return names

    def _problem_payload(self, meta: ProblemMeta, d: Path) -> dict:
        question_md = (d / "question.md").read_text() if (d / "question.md").exists() else ""
        theory_md = (d / "theory.md").read_text() if (d / "theory.md").exists() else ""
        is_derivation = meta.format == "markdown"
        if is_derivation:
            code = (d / "solution.md").read_text() if (d / "solution.md").exists() else ""
            open_test_names = []
            hidden_test_count = 0
        else:
            code = (d / "solution.py").read_text() if (d / "solution.py").exists() else ""
            open_test_names = self._extract_test_names(d / "tests_open.py")
            hidden_test_count = len(self._extract_test_names(d / "tests_hidden.py"))
        chat_history = self.session.load_chat(meta.id) if self.session else []
        return {
            "id": meta.id,
            "title": meta.title,
            "category": meta.category,
            "difficulty": meta.difficulty.value,
            "format": meta.format,
            "status": meta.status.value,
            "attempts": meta.attempts,
            "question_md": question_md,
            "theory_md": theory_md,
            "code": code,
            "open_test_names": open_test_names,
            "hidden_test_count": hidden_test_count,
            "chat_history": chat_history,
            "user_rating": meta.user_rating,
        }

    def _start_pool(self) -> None:
        if self._pool_task and not self._pool_task.done():
            return
        if self._pooled_problem is not None:
            return
        self._pool_task = asyncio.create_task(self._pool_generate())

    def _make_progress_callback(self, loop: asyncio.AbstractEventLoop) -> tuple:
        """Create a progress callback and tracker for use from sync threads."""
        progress = GenerationProgress()

        def _label(step: str, data: dict) -> str:
            if step == "generating":
                return "Generating problem..."
            if step == "generated":
                return "Validating solution..."
            if step == "validating":
                attempt = data.get("attempt", 1)
                if attempt > 1:
                    return f"Validating solution (attempt {attempt})..."
                return "Validating solution..."
            if step == "fixing":
                return "Fixing problem..."
            if step == "fixed":
                return "Validating solution..."
            return step

        def on_progress(step: str, data: dict) -> None:
            if step in ("generated", "fixed"):
                progress.add_usage(data)
            msg = {
                "type": "generating_progress",
                "step": _label(step, data),
                **progress.to_dict(),
            }
            asyncio.run_coroutine_threadsafe(self.send(msg), loop)

        return on_progress, progress

    async def _pool_generate(self) -> None:
        if self.session is None:
            return
        try:
            loop = asyncio.get_event_loop()
            on_progress, _ = self._make_progress_callback(loop)
            meta, problem_dir = await asyncio.to_thread(
                self.session.start_problem, False, on_progress=on_progress
            )
            self._pooled_problem = (meta, problem_dir)
        except Exception:
            self._pooled_problem = None

    async def _generate_next(self, prompt: str = "") -> None:
        assert self.session is not None
        self._generate_cancelled = False
        replay_id = self.session.pick_replay_or_new() if not prompt else None
        if replay_id:
            meta, problem_dir = await asyncio.to_thread(self.session.replay_problem, replay_id)
            if meta and problem_dir:
                self.current_problem = meta
                self.current_problem_dir = problem_dir
                payload = self._problem_payload(meta, problem_dir)
                await self.send({"type": "problem_loaded", "problem": payload})
                self._start_pool()
                return

        if not prompt:
            pool_ready = self._pooled_problem is not None
            pool_running = self._pool_task and not self._pool_task.done()

            if not pool_ready and pool_running:
                await self.send({"type": "generating"})
                await self.send_log('<span class="dim">Loading next problem...</span>')
                try:
                    if self._pool_task is not None:
                        await self._pool_task
                except Exception:
                    pass

            if self._generate_cancelled:
                return

            if self._pooled_problem is not None:
                meta, problem_dir = self._pooled_problem
                self._pooled_problem = None
                if self._generate_cancelled:
                    if self.session is not None:
                        self.session.delete_problem(meta.id)
                    return
                state = self.session._load_state()
                state.current_problem_id = meta.id
                self.session._save_state(state)
                self.current_problem = meta
                self.current_problem_dir = problem_dir
                payload = self._problem_payload(meta, problem_dir)
                await self.send({"type": "problem_loaded", "problem": payload})
                await self.send({"type": "clear_log"})
                self._start_pool()
                return

        await self.send({"type": "generating"})
        await self.send({"type": "clear_log"})
        loop = asyncio.get_event_loop()
        on_progress, progress = self._make_progress_callback(loop)
        try:
            next_meta, next_problem_dir = await asyncio.to_thread(
                self.session.start_problem, user_prompt=prompt, on_progress=on_progress
            )
            if self._generate_cancelled:
                if self.session is not None:
                    self.session.delete_problem(next_meta.id)
                return
            self.current_problem = next_meta
            self.current_problem_dir = next_problem_dir
            payload = self._problem_payload(next_meta, next_problem_dir)
            await self.send({"type": "problem_loaded", "problem": payload})
            await self.send({"type": "clear_log"})
            self._start_pool()
        except Exception as e:
            if not self._generate_cancelled:
                await self.send_log(f'<span class="c-error">Error: {e}</span>')
