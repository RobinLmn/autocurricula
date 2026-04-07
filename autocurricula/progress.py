from __future__ import annotations

from pathlib import Path

from .models import ProblemMeta, ProblemStatus, ProgressState


def load_progress(progress_file: Path) -> ProgressState:
    if progress_file.exists():
        return ProgressState.model_validate_json(progress_file.read_text())
    return ProgressState()


def save_progress(state: ProgressState, progress_file: Path) -> None:
    progress_file.write_text(state.model_dump_json(indent=2))


def get_current_problem(state: ProgressState) -> ProblemMeta | None:
    if state.current_problem_id and state.current_problem_id in state.problems:
        return state.problems[state.current_problem_id]
    return None


def history_summary(state: ProgressState, role: str | None = None) -> str:
    problems = list(state.problems.values())
    if role:
        problems = [p for p in problems if p.role == role]

    if not problems:
        return "No problems attempted yet."

    solved = [p for p in problems if p.status == ProblemStatus.SOLVED]
    failed = [p for p in problems if p.status == ProblemStatus.FAILED]
    scaffolded = [p for p in problems if p.status == ProblemStatus.SCAFFOLDED]

    by_category: dict[str, list[ProblemMeta]] = {}
    for p in problems:
        by_category.setdefault(p.category, []).append(p)

    lines = [
        f"Total problems: {len(problems)} (solved: {len(solved)}, failed: {len(failed)}, scaffolded: {len(scaffolded)})",
    ]

    for cat, cat_problems in by_category.items():
        cat_solved = sum(1 for p in cat_problems if p.status == ProblemStatus.SOLVED)
        cat_total = len(cat_problems)
        lines.append(f"  {cat}: {cat_solved}/{cat_total} solved")

    recent = sorted(problems, key=lambda p: p.created_at)[-5:]
    lines.append("Recent problems:")
    rating_labels = {1: "trivial", 2: "easy", 3: "medium", 4: "hard", 5: "brutal"}
    for p in recent:
        rating_str = f", user rated: {rating_labels.get(p.user_rating, '?')}" if p.user_rating else ""
        lines.append(f"  - [{p.difficulty.value}] {p.title} ({p.category}): {p.status.value}{rating_str}")

    # Highlight high-regret problems (solved but rated hard/brutal)
    high_regret = [p for p in problems if p.status == ProblemStatus.SOLVED and p.user_rating and p.user_rating >= 4]
    if high_regret:
        lines.append("High-regret problems (solved but user found hard/brutal -- consider similar topics):")
        for p in high_regret:
            lines.append(f"  - {p.title} ({p.category}, {p.difficulty.value}, rated {rating_labels[p.user_rating]})")

    return "\n".join(lines)


