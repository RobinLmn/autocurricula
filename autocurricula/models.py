from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ProblemStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SOLVED = "solved"
    FAILED = "failed"
    SKIPPED = "skipped"
    SCAFFOLDED = "scaffolded"


class ProblemMeta(BaseModel):
    id: str
    title: str
    role: str
    category: str
    difficulty: Difficulty
    format: str = "python"  # "python" or "markdown"
    status: ProblemStatus = ProblemStatus.IN_PROGRESS
    created_at: datetime = Field(default_factory=datetime.now)
    solved_at: datetime | None = None
    attempts: int = 0
    parent_problem: str | None = None
    prerequisite_of: str | None = None
    user_rating: int | None = None  # 1=trivial, 2=easy, 3=medium, 4=hard, 5=brutal
    tags: list[str] = Field(default_factory=list)
    source: str = "generated"


class ProgressState(BaseModel):
    current_role: str | None = None
    current_problem_id: str | None = None
    problems: dict[str, ProblemMeta] = Field(default_factory=dict)
    session_count: int = 0


class GeneratedContent(BaseModel):
    """Unified output from the problem generator. Claude picks everything."""

    title: str
    category: str
    difficulty: str
    format: str  # "python" or "markdown"
    tags: list[str] = Field(default_factory=list)
    question: str
    theory: str
    solution_template: str
    reference_solution: str
    tests_open: str = ""
    tests_hidden: str = ""


# Keep these for scaffold generation (which targets a specific format)
class GeneratedProblem(BaseModel):
    title: str
    category: str
    question: str
    theory: str
    tests_open: str
    tests_hidden: str
    solution_template: str
    reference_solution: str


class GeneratedDerivation(BaseModel):
    title: str
    category: str
    question: str
    theory: str
    solution_template: str
    reference_solution: str


class SubmissionVerdict(BaseModel):
    decision: str  # "solved", "retry", "move_on"
    feedback: str  # Claude's detailed feedback
    next_difficulty: str | None = None  # suggestion for next problem
