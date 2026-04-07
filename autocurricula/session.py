from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from .engine import (
    fix_problem,
    generate_derivation_scaffold,
    generate_next_problem,
    generate_scaffold,
    review_derivation,
    review_submission,
)
from .models import (
    Difficulty,
    GeneratedDerivation,
    GeneratedProblem,
    ProblemMeta,
    ProblemStatus,
    ProgressState,
)
from .progress import (
    get_current_problem,
    history_summary,
    load_progress,
    save_progress,
)
from .runner import run_tests
from .workspace import get_description, get_problems_dir, get_progress_file


class Session:
    """Workspace-bound session managing problems and progress."""

    def __init__(self, role: str, workspace_dir: Path) -> None:
        self.role = role
        self.workspace_dir = workspace_dir
        self.problems_dir = get_problems_dir(workspace_dir)
        self.progress_file = get_progress_file(workspace_dir)
        self.problems_dir.mkdir(parents=True, exist_ok=True)

    def _problem_dir(self, problem_id: str) -> Path:
        return self.problems_dir / problem_id

    def _chat_file(self, problem_id: str) -> Path:
        return self._problem_dir(problem_id) / "chat.json"

    def load_chat(self, problem_id: str) -> list[dict[Any, Any]]:
        f = self._chat_file(problem_id)
        if f.exists():
            try:
                return cast(list[dict[Any, Any]], json.loads(f.read_text()))
            except (json.JSONDecodeError, ValueError):
                return []
        return []

    def append_chat(self, problem_id: str, role: str, content: str) -> None:
        history = self.load_chat(problem_id)
        history.append({"role": role, "content": content})
        self._chat_file(problem_id).write_text(json.dumps(history, indent=2))

    def clear_chat(self, problem_id: str) -> None:
        f = self._chat_file(problem_id)
        if f.exists():
            f.unlink()

    def _write_problem_files(self, problem_id: str, generated: GeneratedProblem, meta: ProblemMeta) -> Path:
        d = self._problem_dir(problem_id)
        d.mkdir(parents=True, exist_ok=True)

        (d / "question.md").write_text(generated.question)
        (d / "theory.md").write_text(generated.theory)
        (d / "tests_open.py").write_text(generated.tests_open)
        (d / "tests_hidden.py").write_text(generated.tests_hidden)
        (d / "solution.py").write_text(generated.solution_template)
        (d / "template.py").write_text(generated.solution_template)
        (d / "meta.json").write_text(meta.model_dump_json(indent=2))

        return d

    def _write_derivation_files(self, problem_id: str, generated: GeneratedDerivation, meta: ProblemMeta) -> Path:
        d = self._problem_dir(problem_id)
        d.mkdir(parents=True, exist_ok=True)

        (d / "question.md").write_text(generated.question)
        (d / "theory.md").write_text(generated.theory)
        (d / "solution.md").write_text(generated.solution_template)
        (d / "template.md").write_text(generated.solution_template)
        (d / "reference.md").write_text(generated.reference_solution)
        (d / "meta.json").write_text(meta.model_dump_json(indent=2))

        return d

    def _validate_problem(
        self,
        problem_id: str,
        generated: GeneratedProblem,
        meta: ProblemMeta,
        max_attempts: int = 3,
    ) -> GeneratedProblem:
        """Validate a generated problem by running the reference solution against the tests.

        If tests fail, ask Claude to fix the problem and retry up to max_attempts times.
        """
        d = self._problem_dir(problem_id)

        for attempt in range(max_attempts):
            # Write reference solution as solution.py for test execution
            d.mkdir(parents=True, exist_ok=True)
            (d / "tests_open.py").write_text(generated.tests_open)
            (d / "tests_hidden.py").write_text(generated.tests_hidden)
            (d / "solution.py").write_text(generated.reference_solution)

            open_result = run_tests(str(d), hidden=False)
            if not open_result.passed:
                generated = fix_problem(generated, f"Open tests failed:\n{open_result.output}")
                continue

            hidden_result = run_tests(str(d), hidden=True)
            if not hidden_result.passed:
                generated = fix_problem(generated, f"Hidden tests failed:\n{hidden_result.output}")
                continue

            # All tests pass
            return generated

        return generated

    def _load_state(self) -> ProgressState:
        return load_progress(self.progress_file)

    def _save_state(self, state: ProgressState) -> None:
        save_progress(state, self.progress_file)

    def _load_problem_from_dir(self, problem_dir: Path) -> ProblemMeta | None:
        meta_file = problem_dir / "meta.json"
        if meta_file.exists():
            return ProblemMeta.model_validate_json(meta_file.read_text())
        return None

    def load_problem_db(self) -> dict[str, ProblemMeta]:
        db: dict[str, ProblemMeta] = {}
        if not self.problems_dir.exists():
            return db
        for d in self.problems_dir.iterdir():
            if d.is_dir():
                meta = self._load_problem_from_dir(d)
                if meta:
                    db[meta.id] = meta
        return db

    def get_current(self) -> ProblemMeta | None:
        state = self._load_state()
        return get_current_problem(state)

    def start_problem(
        self,
        set_current: bool = True,
    ) -> tuple[ProblemMeta, Path]:
        state = self._load_state()
        state.current_role = self.role

        problem_id = f"prob_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        summary = history_summary(state, self.role)
        description = get_description(self.workspace_dir) or self.role

        generated = generate_next_problem(self.role, description, summary)

        if generated.difficulty in ("easy", "medium", "hard"):
            difficulty = Difficulty(generated.difficulty)
        else:
            difficulty = Difficulty.MEDIUM
        fmt = generated.format if generated.format in ("python", "markdown") else "python"

        meta = ProblemMeta(
            id=problem_id,
            title=generated.title,
            role=self.role,
            category=generated.category,
            difficulty=difficulty,
            format=fmt,
        )

        if fmt == "markdown":
            deriv = GeneratedDerivation(
                title=generated.title,
                category=generated.category,
                question=generated.question,
                theory=generated.theory,
                solution_template=generated.solution_template,
                reference_solution=generated.reference_solution,
            )
            self._write_derivation_files(problem_id, deriv, meta)
        else:
            prob = GeneratedProblem(
                title=generated.title,
                category=generated.category,
                question=generated.question,
                theory=generated.theory,
                tests_open=generated.tests_open,
                tests_hidden=generated.tests_hidden,
                solution_template=generated.solution_template,
                reference_solution=generated.reference_solution,
            )
            prob = self._validate_problem(problem_id, prob, meta)
            self._write_problem_files(problem_id, prob, meta)

        state.problems[problem_id] = meta
        if set_current:
            state.current_problem_id = problem_id
        state.session_count += 1
        self._save_state(state)

        return meta, self._problem_dir(problem_id)

    def replay_problem(self, problem_id: str) -> tuple[ProblemMeta | None, Path | None]:
        d = self._problem_dir(problem_id)
        meta = self._load_problem_from_dir(d)
        if meta is None:
            return None, None

        meta.status = ProblemStatus.IN_PROGRESS
        meta.attempts = 0
        meta.solved_at = None
        meta.user_rating = None
        meta.created_at = datetime.now()

        if meta.format == "markdown":
            template_file = d / "template.md"
            solution_file = d / "solution.md"
        else:
            template_file = d / "template.py"
            solution_file = d / "solution.py"
        if template_file.exists():
            solution_file.write_text(template_file.read_text())

        (d / "meta.json").write_text(meta.model_dump_json(indent=2))

        state = self._load_state()
        state.problems[problem_id] = meta
        state.current_problem_id = problem_id
        self._save_state(state)

        return meta, d

    def test_solution(self):
        state = self._load_state()
        problem = get_current_problem(state)
        if problem is None:
            return None, None

        result = run_tests(str(self._problem_dir(problem.id)), hidden=False)
        return problem, result

    def submit_solution(self):
        state = self._load_state()
        problem = get_current_problem(state)
        if problem is None:
            return None, None, None, None

        problem.attempts += 1
        d = self._problem_dir(problem.id)

        open_result = run_tests(str(d), hidden=False)
        hidden_result = run_tests(str(d), hidden=True)

        all_passed = open_result.passed and hidden_result.passed
        combined_output = f"Open tests:\n{open_result.output}\n\nHidden tests:\n{hidden_result.output}"

        question = (d / "question.md").read_text()
        user_code = (d / "solution.py").read_text()

        chat_history = self.load_chat(problem.id)
        verdict = review_submission(
            question=question,
            user_code=user_code,
            test_output=combined_output,
            all_tests_passed=all_passed,
            difficulty=problem.difficulty.value,
            role=problem.role,
            attempts=problem.attempts,
            chat_history=chat_history,
        )

        if verdict.decision == "solved":
            problem.status = ProblemStatus.SOLVED
            problem.solved_at = datetime.now()
        elif verdict.decision == "move_on":
            problem.status = ProblemStatus.FAILED

        (d / "meta.json").write_text(problem.model_dump_json(indent=2))
        self._save_state(state)

        return problem, open_result, hidden_result, verdict

    def submit_derivation(self):
        state = self._load_state()
        problem = get_current_problem(state)
        if problem is None:
            return None, None

        problem.attempts += 1
        d = self._problem_dir(problem.id)

        user_answer = (d / "solution.md").read_text() if (d / "solution.md").exists() else ""
        question = (d / "question.md").read_text()
        reference = (d / "reference.md").read_text() if (d / "reference.md").exists() else ""

        chat_history = self.load_chat(problem.id)
        verdict = review_derivation(
            question=question,
            user_answer=user_answer,
            reference_solution=reference,
            difficulty=problem.difficulty.value,
            role=problem.role,
            attempts=problem.attempts,
            chat_history=chat_history,
        )

        if verdict.decision == "solved":
            problem.status = ProblemStatus.SOLVED
            problem.solved_at = datetime.now()
        elif verdict.decision == "move_on":
            problem.status = ProblemStatus.FAILED

        (d / "meta.json").write_text(problem.model_dump_json(indent=2))
        self._save_state(state)

        return problem, verdict

    def scaffold_problem(self) -> tuple[ProblemMeta | None, ProblemMeta | None, Path | None]:
        state = self._load_state()
        original = get_current_problem(state)
        if original is None:
            return None, None, None

        d = self._problem_dir(original.id)
        question = (d / "question.md").read_text()

        problem_id = f"scaffold_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        if original.format == "markdown":
            user_answer = (d / "solution.md").read_text() if (d / "solution.md").exists() else ""
            generated = generate_derivation_scaffold(
                question, user_answer, original.role, original.category, history_summary(state, original.role)
            )
            scaffold_meta = ProblemMeta(
                id=problem_id,
                title=generated.title,
                role=original.role,
                category=original.category,
                difficulty=Difficulty.EASY,
                format="markdown",
                parent_problem=original.id,
            )
            self._write_derivation_files(problem_id, generated, scaffold_meta)
        else:
            user_code = (d / "solution.py").read_text()
            prob = generate_scaffold(
                question, user_code, original.role, original.category, history_summary(state, original.role)
            )
            scaffold_meta = ProblemMeta(
                id=problem_id,
                title=prob.title,
                role=original.role,
                category=original.category,
                difficulty=Difficulty.EASY,
                format="python",
                parent_problem=original.id,
            )
            prob = self._validate_problem(problem_id, prob, scaffold_meta)
            self._write_problem_files(problem_id, prob, scaffold_meta)

        original.status = ProblemStatus.SCAFFOLDED
        original.prerequisite_of = problem_id
        (self._problem_dir(original.id) / "meta.json").write_text(original.model_dump_json(indent=2))

        state.problems[problem_id] = scaffold_meta
        state.current_problem_id = problem_id
        self._save_state(state)

        return original, scaffold_meta, self._problem_dir(problem_id)

    def give_up(self) -> ProblemMeta | None:
        state = self._load_state()
        problem = get_current_problem(state)
        if problem is None:
            return None

        problem.status = ProblemStatus.FAILED if problem.attempts > 0 else ProblemStatus.SKIPPED
        (self._problem_dir(problem.id) / "meta.json").write_text(problem.model_dump_json(indent=2))

        if problem.parent_problem and problem.parent_problem in state.problems:
            state.current_problem_id = problem.parent_problem
            parent = state.problems[problem.parent_problem]
            parent.status = ProblemStatus.IN_PROGRESS
            parent.prerequisite_of = None
            (self._problem_dir(parent.id) / "meta.json").write_text(parent.model_dump_json(indent=2))

        self._save_state(state)
        return problem

    def rate_problem(self, problem_id: str, rating: int) -> ProblemMeta | None:
        """Record the user's difficulty rating (1-5) for a problem."""
        state = self._load_state()
        problem = state.problems.get(problem_id)
        if problem is None:
            return None
        problem.user_rating = rating
        d = self._problem_dir(problem_id)
        (d / "meta.json").write_text(problem.model_dump_json(indent=2))
        self._save_state(state)
        return problem

    def pick_replay_or_new(self) -> str | None:
        """Return a problem_id to replay if there's a high-regret solved problem, else None.

        High-regret = solved but user_rating >= 3 (medium/hard/brutal).
        Problems rated 1 (trivial) or 2 (easy) are considered mastered.
        ~30% chance to replay a high-regret problem instead of generating new.
        """
        state = self._load_state()
        high_regret = [
            p for p in state.problems.values()
            if p.status == ProblemStatus.SOLVED
            and p.user_rating is not None
            and p.user_rating >= 3
        ]
        if not high_regret:
            return None
        # 30% chance to replay a high-regret problem
        if random.random() > 0.3:
            return None
        # Weight by rating: higher rating = more likely to replay
        weights: list[float] = [float(p.user_rating or 1) for p in high_regret]
        chosen = cast(ProblemMeta, random.choices(high_regret, weights=weights, k=1)[0])
        return chosen.id

    def resume_parent(self) -> tuple[ProblemMeta | None, Path | None]:
        state = self._load_state()
        problem = get_current_problem(state)
        if problem is None or problem.parent_problem is None:
            return None, None

        parent = state.problems.get(problem.parent_problem)
        if parent is None:
            return None, None

        parent.status = ProblemStatus.IN_PROGRESS
        state.current_problem_id = parent.id
        (self._problem_dir(parent.id) / "meta.json").write_text(parent.model_dump_json(indent=2))
        self._save_state(state)

        return parent, self._problem_dir(parent.id)
