from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .models import ProblemStatus
from .test_parsing import extract_failure_details, parse_pytest_output

if TYPE_CHECKING:
    from .session_handler import SessionHandler


class CommandsMixin:
    """Command handlers (_cmd_*), mixed into SessionHandler."""

    async def _cmd_run(self: SessionHandler) -> None:
        if self.current_problem is None or self._cmd_lock.locked():
            return
        if self.current_problem.format == "markdown":
            return
        await self.set_busy(True)
        await self.send({"type": "clear_log"})
        try:
            from .runner import run_solution
            result = await asyncio.to_thread(
                run_solution, str(self.current_problem_dir)
            )
            await self.send({
                "type": "log",
                "text": result.output,
                "error": not result.passed,
            })
        except Exception as e:
            await self.send_log(f'<span class="c-error">error: {e}</span>')
        finally:
            await self.set_busy(False)

    async def _cmd_test(self: SessionHandler) -> None:
        if self.current_problem is None or self._cmd_lock.locked():
            return
        if self.current_problem.format == "markdown":
            return
        await self.set_busy(True)
        try:
            meta, result = await asyncio.to_thread(self.session.test_solution)
            if result is None:
                await self.send_log('<span class="c-error">no active problem</span>')
                return
            tests = parse_pytest_output(result.output)
            details = extract_failure_details(result.output) if not result.passed else {}
            for t in tests:
                if t["status"] == "failed" and t["name"] in details:
                    t["detail"] = details[t["name"]]
            await self.send({
                "type": "test_results",
                "label": "Open Tests",
                "passed": result.passed,
                "num_passed": result.num_passed,
                "num_failed": result.num_failed,
                "tests": tests,
            })
        except Exception as e:
            await self.send_log(f'<span class="c-error">error: {e}</span>')
        finally:
            await self.set_busy(False)

    async def _cmd_submit(self: SessionHandler) -> None:
        if self.current_problem is None or self._cmd_lock.locked():
            return
        if self.current_problem.format == "markdown":
            await self._cmd_submit_derivation()
            return
        await self.set_busy(True)
        await self.send_log('<span class="dim">Submitting for review...</span>')
        try:
            meta, open_result, hidden_result, verdict = await asyncio.to_thread(
                self.session.submit_solution
            )
            if verdict is None:
                await self.send_log('<span class="c-error">no active problem</span>')
                return
            open_tests = parse_pytest_output(open_result.output)
            hidden_tests = parse_pytest_output(hidden_result.output)
            open_details = extract_failure_details(open_result.output) if not open_result.passed else {}
            hidden_details = extract_failure_details(hidden_result.output) if not hidden_result.passed else {}
            for t in open_tests:
                if t["status"] == "failed" and t["name"] in open_details:
                    t["detail"] = open_details[t["name"]]
            for t in hidden_tests:
                if t["status"] == "failed" and t["name"] in hidden_details:
                    t["detail"] = hidden_details[t["name"]]
            await self.send({
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
            })
            await self._send_verdict(meta, verdict)
        except Exception as e:
            await self.send_log(f'<span class="c-error">error: {e}</span>')
        finally:
            await self.set_busy(False)

    async def _cmd_submit_derivation(self: SessionHandler) -> None:
        await self.set_busy(True)
        await self.send_log('<span class="dim">Submitting derivation for review...</span>')
        try:
            meta, verdict = await asyncio.to_thread(
                self.session.submit_derivation
            )
            if verdict is None:
                await self.send_log('<span class="c-error">no active problem</span>')
                return
            await self._send_verdict(meta, verdict)
        except Exception as e:
            await self.send_log(f'<span class="c-error">error: {e}</span>')
        finally:
            await self.set_busy(False)

    async def _send_verdict(self: SessionHandler, meta, verdict) -> None:
        has_parent = False
        if verdict.decision == "solved":
            problem = self.session.get_current()
            if problem and problem.parent_problem:
                has_parent = True
        label = {"solved": "Solved!", "retry": "Not quite", "move_on": "Moving on"}.get(verdict.decision, "Review")
        self.session.append_chat(meta.id, "assistant", f"**{label}**\n\n{verdict.feedback}")
        await self.send({
            "type": "verdict",
            "decision": verdict.decision,
            "feedback": verdict.feedback,
            "has_parent": has_parent,
            "problem_id": meta.id,
        })

    async def _cmd_scaffold(self: SessionHandler) -> None:
        if self.current_problem is None or self._cmd_lock.locked():
            return
        await self.set_busy(True)
        await self.send({"type": "generating"})
        await self.send({"type": "clear_log"})
        await self.send_log('<span class="dim">Generating easier prerequisite...</span>')
        try:
            original, scaffold_meta, scaffold_dir = await asyncio.to_thread(
                self.session.scaffold_problem
            )
            if scaffold_meta and scaffold_dir:
                self.current_problem = scaffold_meta
                self.current_problem_dir = scaffold_dir
                payload = self._problem_payload(scaffold_meta, scaffold_dir)
                await self.send({"type": "problem_loaded", "problem": payload})
                await self.send({"type": "clear_log"})
            else:
                await self.send_log('<span class="c-error">Could not generate scaffold</span>')
        except Exception as e:
            await self.send_log(f'<span class="c-error">error: {e}</span>')
        finally:
            await self.set_busy(False)

    async def _cmd_give_up(self: SessionHandler) -> None:
        if self.current_problem is None:
            await self.send_log('<span class="c-error">no active problem</span>')
            return
        await self.send({
            "type": "confirm",
            "message": f"Skip '{self.current_problem.title}'?",
        })
        try:
            while True:
                data = await asyncio.wait_for(self.ws.receive_json(), timeout=30)
                if data.get("type") == "confirm_response":
                    if data.get("confirmed"):
                        meta = self.session.give_up()
                        await self.send_log(f'<span class="dim">Skipped: {meta.title}</span>')
                        current = self.session.get_current()
                        if (current and current.id != meta.id
                                and current.status == ProblemStatus.IN_PROGRESS):
                            self.current_problem = current
                            self.current_problem_dir = self.session._problem_dir(current.id)
                            payload = self._problem_payload(current, self.current_problem_dir)
                            await self.send({"type": "problem_loaded", "problem": payload})
                        else:
                            await self._generate_next()
                    return
        except TimeoutError:
            return

    async def _cmd_show(self: SessionHandler) -> None:
        if self.current_problem and self.current_problem_dir:
            payload = self._problem_payload(self.current_problem, self.current_problem_dir)
            await self.send({"type": "problem_loaded", "problem": payload})
        else:
            await self.send_log('<span class="c-error">no active problem</span>')

    async def _cmd_problems(self: SessionHandler) -> None:
        db = self.session.load_problem_db()
        problems = []
        for p in sorted(db.values(), key=lambda x: x.created_at, reverse=True):
            problems.append({
                "id": p.id,
                "title": p.title,
                "category": p.category,
                "difficulty": p.difficulty.value,
                "status": p.status.value,
                "attempts": p.attempts,
            })
        await self.send({"type": "problems_list", "problems": problems})

    async def _cmd_progress(self: SessionHandler) -> None:
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
        await self.send({
            "type": "progress_data",
            "role": self.session.role,
            "solved": solved,
            "failed": failed,
            "total": total,
            "rate": round(rate, 1),
            "categories": by_cat,
        })

    async def _cmd_replay(self: SessionHandler, args: list[str]) -> None:
        if not args:
            await self.send_log('<span class="dim">usage: /replay &lt;problem_id&gt;</span>')
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

    async def _cmd_resume(self: SessionHandler) -> None:
        problem = self.session.get_current()
        if problem is None:
            from .progress import load_progress, save_progress
            state = load_progress(self.session.progress_file)
            in_progress = [
                p for p in state.problems.values()
                if p.status == ProblemStatus.IN_PROGRESS
            ]
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
