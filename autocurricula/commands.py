from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .models import ProblemMeta, ProblemStatus, SubmissionVerdict
from .test_parsing import extract_failure_details, extract_test_assertions, parse_pytest_output

if TYPE_CHECKING:
    from .session import Session


class _WsProto(Protocol):
    async def receive_json(self) -> Any: ...


class _CommandsProto(Protocol):
    session: Session | None
    current_problem: ProblemMeta | None
    current_problem_dir: Path | None
    _cmd_lock: asyncio.Lock
    _confirm_future: asyncio.Future[bool] | None
    _pooled_problem: tuple[ProblemMeta, Path] | None
    ws: _WsProto

    async def send(self, msg: dict) -> None: ...
    async def send_log(self, html: str, style: str = ...) -> None: ...
    async def set_busy(self, busy: bool) -> None: ...
    def _problem_payload(self, meta: ProblemMeta, d: Path) -> dict: ...
    async def _send_verdict(self, meta: ProblemMeta, verdict: SubmissionVerdict) -> None: ...
    async def _generate_next(self) -> None: ...
    async def _cmd_submit_derivation(self) -> None: ...


class CommandsMixin:
    """Command handlers (_cmd_*), mixed into SessionHandler."""

    session: Session | None
    current_problem: ProblemMeta | None
    current_problem_dir: Path | None
    _pooled_problem: tuple[ProblemMeta, Path] | None
    _confirm_future: asyncio.Future[bool] | None

    async def _cmd_run(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.current_problem is None or self._cmd_lock.locked():
            return
        if self.current_problem.format == "markdown":
            return
        async with self._cmd_lock:
            await self.set_busy(True)
            await self.send({"type": "clear_log"})
            try:
                from .runner import run_solution

                result = await asyncio.to_thread(run_solution, str(self.current_problem_dir))
                await self.send(
                    {
                        "type": "log",
                        "text": result.output,
                        "error": not result.passed,
                    }
                )
            except Exception as e:
                await self.send_log(f'<span class="c-error">error: {e}</span>')
            finally:
                await self.set_busy(False)

    async def _cmd_test(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.current_problem is None or self._cmd_lock.locked():
            return
        if self.current_problem.format == "markdown":
            return
        if self.session is None:
            return
        async with self._cmd_lock:
            await self.set_busy(True)
            try:
                meta, result = await asyncio.to_thread(self.session.test_solution)
                if result is None:
                    await self.send_log('<span class="c-error">no active problem</span>')
                    return
                tests = parse_pytest_output(result.output)
                if not tests and not result.passed:
                    tests = [{"name": "collection", "status": "error", "detail": result.output.strip()}]
                    result.num_failed = 1
                details = extract_failure_details(result.output) if not result.passed else {}
                assertions = (
                    extract_test_assertions(self.current_problem_dir / "tests_open.py")
                    if self.current_problem_dir
                    else {}
                )
                for t in tests:
                    if t["status"] == "failed" and t["name"] in details:
                        t["detail"] = details[t["name"]]
                    elif t["status"] == "passed" and t["name"] in assertions:
                        t["detail"] = assertions[t["name"]]
                await self.send(
                    {
                        "type": "test_results",
                        "label": "Open Tests",
                        "passed": result.passed,
                        "num_passed": result.num_passed,
                        "num_failed": result.num_failed,
                        "tests": tests,
                    }
                )
            except Exception as e:
                await self.send_log(f'<span class="c-error">error: {e}</span>')
            finally:
                await self.set_busy(False)

    async def _cmd_submit(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.current_problem is None or self._cmd_lock.locked():
            return
        if self.current_problem.format == "markdown":
            await self._cmd_submit_derivation()
            return
        if self.session is None:
            return
        async with self._cmd_lock:
            await self.set_busy(True)
            await self.send_log('<span class="dim">Submitting for review...</span>')
            try:
                meta, open_result, hidden_result, verdict = await asyncio.to_thread(self.session.submit_solution)
                if verdict is None:
                    await self.send_log('<span class="c-error">no active problem</span>')
                    return
                open_tests = parse_pytest_output(open_result.output)
                hidden_tests = parse_pytest_output(hidden_result.output)
                if not open_tests and not open_result.passed:
                    open_tests = [{"name": "collection", "status": "error", "detail": open_result.output.strip()}]
                    open_result.num_failed = 1
                if not hidden_tests and not hidden_result.passed:
                    hidden_tests = [{"name": "collection", "status": "error", "detail": hidden_result.output.strip()}]
                    hidden_result.num_failed = 1
                open_details = extract_failure_details(open_result.output) if not open_result.passed else {}
                hidden_details = extract_failure_details(hidden_result.output) if not hidden_result.passed else {}
                open_assertions = (
                    extract_test_assertions(self.current_problem_dir / "tests_open.py")
                    if self.current_problem_dir
                    else {}
                )
                hidden_assertions = (
                    extract_test_assertions(self.current_problem_dir / "tests_hidden.py")
                    if self.current_problem_dir
                    else {}
                )
                for t in open_tests:
                    if t["status"] == "failed" and t["name"] in open_details:
                        t["detail"] = open_details[t["name"]]
                    elif t["status"] == "passed" and t["name"] in open_assertions:
                        t["detail"] = open_assertions[t["name"]]
                for t in hidden_tests:
                    if t["status"] == "failed" and t["name"] in hidden_details:
                        t["detail"] = hidden_details[t["name"]]
                    elif t["status"] == "passed" and t["name"] in hidden_assertions:
                        t["detail"] = hidden_assertions[t["name"]]
                await self.send(
                    {
                        "type": "test_results",
                        "label": "Submission",
                        "passed": open_result.passed and hidden_result.passed,
                        "num_passed": open_result.num_passed + hidden_result.num_passed,
                        "num_failed": open_result.num_failed + hidden_result.num_failed,
                        "tests": open_tests + hidden_tests,
                        "sections": [
                            {"label": "Open Tests", "passed": open_result.passed, "tests": open_tests},
                            {"label": "Hidden Tests", "passed": hidden_result.passed, "tests": hidden_tests},
                        ],
                    }
                )
                await self._send_verdict(meta, verdict)
            except Exception as e:
                await self.send_log(f'<span class="c-error">error: {e}</span>')
            finally:
                await self.set_busy(False)

    async def _cmd_submit_derivation(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.session is None:
            return
        await self.set_busy(True)
        await self.send_log('<span class="dim">Submitting derivation for review...</span>')
        try:
            meta, verdict = await asyncio.to_thread(self.session.submit_derivation)
            if verdict is None:
                await self.send_log('<span class="c-error">no active problem</span>')
                return
            await self._send_verdict(meta, verdict)
        except Exception as e:
            await self.send_log(f'<span class="c-error">error: {e}</span>')
        finally:
            await self.set_busy(False)

    async def _send_verdict(self: _CommandsProto, meta: ProblemMeta, verdict: SubmissionVerdict) -> None:  # type: ignore[misc]
        if self.session is None:
            return
        has_parent = False
        if verdict.decision == "solved":
            problem = self.session.get_current()
            if problem and problem.parent_problem:
                has_parent = True
        label = {
            "solved": "Solved!",
            "follow_up": "Follow-up",
            "retry": "Not quite",
            "move_on": "Moving on",
        }.get(verdict.decision, "Review")
        self.session.append_chat(meta.id, "assistant", f"**{label}**\n\n{verdict.feedback}")
        await self.send(
            {
                "type": "verdict",
                "decision": verdict.decision,
                "feedback": verdict.feedback,
                "has_parent": has_parent,
                "problem_id": meta.id,
            }
        )

    async def _cmd_scaffold(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.current_problem is None or self._cmd_lock.locked():
            return
        if self.session is None:
            return
        async with self._cmd_lock:
            await self.set_busy(True)
            await self.send({"type": "generating"})
            await self.send({"type": "clear_log"})
            await self.send_log('<span class="dim">Generating easier prerequisite...</span>')
            try:
                original, scaffold_meta, scaffold_dir = await asyncio.to_thread(self.session.scaffold_problem)
                if scaffold_meta and scaffold_dir:
                    self.current_problem = scaffold_meta
                    self.current_problem_dir = scaffold_dir
                    payload = self._problem_payload(scaffold_meta, scaffold_dir)
                    await self.send({"type": "problem_loaded", "problem": payload})
                    await self.send({"type": "clear_log"})
                else:
                    await self.send(
                        {
                            "type": "chat_response",
                            "text": "Sorry, I couldn't generate a scaffold for this problem."
                            " Try again or ask me for a hint instead.",
                        }
                    )
            except Exception:
                await self.send(
                    {
                        "type": "chat_response",
                        "text": "Sorry, something went wrong while generating the scaffold."
                        " Try again or ask me for a hint instead.",
                    }
                )
            finally:
                await self.set_busy(False)

    async def _cmd_give_up(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.current_problem is None:
            await self.send_log('<span class="c-error">no active problem</span>')
            return
        if self.session is None:
            return
        await self.send(
            {
                "type": "confirm",
                "message": f"Skip '{self.current_problem.title}'?",
            }
        )
        future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
        self._confirm_future = future
        try:
            confirmed = await asyncio.wait_for(future, timeout=30)
        except (TimeoutError, asyncio.CancelledError):
            return
        finally:
            self._confirm_future = None
        if confirmed:
            await self.set_busy(True)
            try:
                meta = self.session.give_up()
                if meta is None:
                    return
                await self.send_log(f'<span class="dim">Skipped: {meta.title}</span>')
                current = self.session.get_current()
                if current and current.id != meta.id and current.status == ProblemStatus.IN_PROGRESS:
                    self.current_problem = current
                    self.current_problem_dir = self.session._problem_dir(current.id)
                    payload = self._problem_payload(current, self.current_problem_dir)
                    await self.send({"type": "problem_loaded", "problem": payload})
                else:
                    self._pooled_problem = None
                    await self._generate_next()
            finally:
                await self.set_busy(False)

    async def _cmd_show(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.current_problem and self.current_problem_dir:
            payload = self._problem_payload(self.current_problem, self.current_problem_dir)
            await self.send({"type": "problem_loaded", "problem": payload})
        else:
            await self.send_log('<span class="c-error">no active problem</span>')

    async def _cmd_problems(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.session is None:
            return
        db = self.session.load_problem_db()
        problems = []
        for p in sorted(db.values(), key=lambda x: x.created_at, reverse=True):
            problems.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "category": p.category,
                    "difficulty": p.difficulty.value,
                    "status": p.status.value,
                    "attempts": p.attempts,
                }
            )
        await self.send({"type": "problems_list", "problems": problems})

    async def _cmd_progress(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.session is None:
            return
        from .progress import load_progress

        state = load_progress(self.session.progress_file)
        problems = list(state.problems.values())
        solved = sum(1 for p in problems if p.status == ProblemStatus.SOLVED)
        failed = sum(1 for p in problems if p.status == ProblemStatus.FAILED)
        total = len(problems)
        rate = (solved / total * 100) if total else 0
        by_cat: dict[str, dict] = {}
        for p in problems:
            cat = p.category
            if cat not in by_cat:
                by_cat[cat] = {"solved": 0, "total": 0}
            by_cat[cat]["total"] += 1
            if p.status == ProblemStatus.SOLVED:
                by_cat[cat]["solved"] += 1
        await self.send(
            {
                "type": "progress_data",
                "role": self.session.role,
                "solved": solved,
                "failed": failed,
                "total": total,
                "rate": round(rate, 1),
                "categories": by_cat,
            }
        )

    async def _cmd_replay(self: _CommandsProto, args: list[str]) -> None:  # type: ignore[misc]
        if not args:
            await self.send_log('<span class="dim">usage: /replay &lt;problem_id&gt;</span>')
            return
        if self.session is None:
            return
        db = self.session.load_problem_db()
        pid_query = args[0]
        matches = [pid for pid in db if pid.endswith(pid_query) or pid == pid_query]
        if not matches:
            await self.send_log(f'<span class="c-error">no match: {pid_query}</span>')
            return
        meta, d = self.session.replay_problem(matches[0])
        if meta and d:
            self.current_problem = meta
            self.current_problem_dir = d
            payload = self._problem_payload(meta, d)
            await self.send({"type": "problem_loaded", "problem": payload})
        else:
            await self.send_log('<span class="c-error">could not load problem</span>')

    async def _cmd_resume(self: _CommandsProto) -> None:  # type: ignore[misc]
        if self.session is None:
            return
        problem = self.session.get_current()
        if problem is None:
            from .progress import load_progress, save_progress

            state = load_progress(self.session.progress_file)
            in_progress = [p for p in state.problems.values() if p.status == ProblemStatus.IN_PROGRESS]
            if not in_progress:
                await self.send_log('<span class="c-error">no in-progress problems</span>')
                return
            problem = sorted(in_progress, key=lambda p: p.created_at)[-1]
            state.current_problem_id = problem.id
            save_progress(state, self.session.progress_file)
        d = self.session._problem_dir(problem.id)
        self.current_problem = problem
        self.current_problem_dir = d
        payload = self._problem_payload(problem, d)
        await self.send({"type": "problem_loaded", "problem": payload})
