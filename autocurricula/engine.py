from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from .models import GeneratedContent, GeneratedDerivation, GeneratedProblem, SubmissionVerdict


def _call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", "--output-format", "text", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude call failed: {result.stderr}")
    return result.stdout.strip()


def name_workspace(user_description: str) -> str:
    """Turn a free-form role description into a concise workspace/role title."""
    prompt = f"""The user described their role/interest for an interview practice platform:

"{user_description}"

Generate a concise role title (2-4 words) that captures this. Examples:
- "I want to practice for MLE interviews" → "Machine Learning Engineer"
- "a mix of quant and ML stuff" → "ML Quant Researcher"
- "backend software engineering" → "Backend Engineer"
- "data science and statistics" → "Data Scientist"

Respond with ONLY the title, nothing else."""

    return _call_claude(prompt)


def _format_chat_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = []
    for msg in history:
        role = "Student" if msg["role"] == "user" else "Tutor"
        lines.append(f"{role}: {msg['content']}")
    return "\n\n".join(lines)


def _build_chat_prompt(
    message: str,
    question: str | None,
    user_code: str | None,
    is_markdown: bool,
    chat_history: list[dict],
) -> str:
    """Build a conversation prompt. System context goes in the first turn only;
    subsequent messages just continue the transcript."""
    parts = []

    if not chat_history:
        # First message: set up the session with rules and problem context
        parts.append(
            "You are a tutor helping a student practice for technical interviews. "
            "This is the start of a session for one problem. Rules for the whole session:\n"
            "- Help the student: explain concepts, clarify the problem, give hints\n"
            "- Do NOT write the solution or give the answer directly\n"
            "- Keep responses concise and conversational\n"
            "- Link library functions to docs when you mention them "
            "(e.g. [`np.mean()`](https://numpy.org/doc/stable/reference/generated/numpy.mean.html))\n"
            "- The app has Run, Test, Submit, Scaffold, and Skip buttons in the toolbar\n"
            "- Before answering, always review the student's latest code below to stay in sync"
        )
        if question:
            parts.append(f"Problem:\n{question}")
    else:
        # Continuing session: replay the conversation
        parts.append("Continuing tutoring session. Conversation so far:")
        for msg in chat_history:
            role = "Student" if msg["role"] == "user" else "Tutor"
            parts.append(f"{role}: {msg['content']}")

    # Always include the student's latest code so the tutor is up to date
    if user_code is not None:
        lang = "markdown" if is_markdown else "python"
        parts.append(f"Student's current code:\n```{lang}\n{user_code}\n```")

    parts.append(f"Student: {message}")

    return "\n\n".join(parts)


def chat_with_claude(
    message: str,
    question: str | None = None,
    user_code: str | None = None,
    is_markdown: bool = False,
    chat_history: list[dict] | None = None,
) -> str:
    """Chat with Claude about the current problem. Uses session-style prompting:
    rules are set in the first message, history carries them forward."""
    prompt = _build_chat_prompt(message, question, user_code, is_markdown, chat_history or [])
    return _call_claude(prompt)


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        result: dict[str, Any] = json.loads(match.group(1))
        return result
    result = json.loads(text)
    return result


def generate_next_problem(
    role: str,
    description: str,
    history_summary: str,
) -> GeneratedContent:
    """Single Claude call that picks difficulty, format, category, and generates the problem."""
    prompt = f"""You are an autocurricula engine: an adaptive system that generates \
interview practice problems tailored to a student's progress.

The student described what they're preparing for:
"{description}"

Their workspace role: {role}

Progress so far:
{history_summary}

Based on this history, decide what the student should practice next. Consider:
- Which categories they've under-practiced or struggled with
- Whether to escalate, maintain, or reduce difficulty
- Whether a coding problem ("python") or written-answer problem ("markdown") fits best
- Avoid repeating recent categories unless the student needs more practice there

Respond ONLY with a JSON block (wrapped in ```json``` markers) with these keys:

- "title": short descriptive title (string)
- "category": lowercase category label, e.g. "algorithms", "probability", "ml", "system design" (string)
- "difficulty": "easy", "medium", or "hard" (string)
- "format": "python" or "markdown" (string)
- "question": full problem statement in markdown. Write it like a real interview question. \
For python: state WHAT to implement, specify inputs/outputs and types, give 1-2 examples. \
For markdown: be specific about what to address, use LaTeX ($...$) for math. \
Do NOT include implementation hints. (string)
- "theory": background theory in markdown covering concepts needed. \
This IS the place for formulas, derivations, and intuitions. 2-4 paragraphs. (string)
- "solution_template": for python: function signature `def solve(...)` with full type hints and `pass`. \
For markdown: section headings that guide the response. (string)
- "reference_solution": complete correct answer (python code or markdown). \
The student never sees this. (string)

For python format ONLY, also include:
- "tests_open": pytest code importing `from solution import solve`, 3-5 basic test functions (string)
- "tests_hidden": pytest code importing `from solution import solve`, 3-5 edge case tests (string)

For python problems:
- numpy, torch, scipy, pandas are available but only use them when natural for the problem
- Use 2-space indentation in all Python code
- Make sure tests are self-contained and correct"""

    raw = _call_claude(prompt)
    data = _extract_json(raw)
    return GeneratedContent(**data)


def fix_problem(generated: GeneratedProblem, test_output: str) -> GeneratedProblem:
    """Ask Claude to fix a generated problem whose reference solution fails its own tests."""
    prompt = f"""You generated an interview practice problem, but the reference solution fails the tests. Fix the issue.

Current problem JSON:
```json
{json.dumps(generated.model_dump(), indent=2)}
```

Test output (failures):
{test_output}

Diagnose whether the bug is in the reference_solution, the tests, or the problem statement. Fix whatever is wrong.

Respond ONLY with a corrected JSON block (wrapped in ```json``` markers) containing ALL the same keys:
- "title", "question", "theory", "tests_open", "tests_hidden", "solution_template", "reference_solution"

Make sure the reference_solution actually passes all tests."""

    raw = _call_claude(prompt)
    data = _extract_json(raw)
    return GeneratedProblem(**data)


def review_submission(
    question: str,
    user_code: str,
    test_output: str,
    all_tests_passed: bool,
    difficulty: str,
    role: str,
    attempts: int,
    chat_history: list[dict] | None = None,
) -> SubmissionVerdict:
    history_text = _format_chat_history(chat_history or [])
    history_section = f"\n\nChat discussion with student:\n{history_text}" if history_text else ""

    prompt = f"""You are reviewing a student's submission for an interview practice problem.

Problem:
{question}

Student's solution:
```python
{user_code}
```

Test results (all tests passed: {all_tests_passed}):
{test_output}{history_section}

Context:
- Role: {role}
- Difficulty: {difficulty}
- Attempts: {attempts}

Review the submission and decide what happens next. Respond ONLY with a JSON block
(wrapped in ```json``` markers) with these exact keys:

- "decision": one of "solved", "retry", or "move_on"
  - "solved": the solution is correct and passes all tests. Congratulate the student.
  - "retry": tests failed or the solution has issues worth fixing. Encourage them to try again.
  - "move_on": the student has been struggling too long (many attempts) and should move to a
    different problem. Mark as unsolved.

- "feedback": detailed feedback string. Include:
  - Whether the solution is correct
  - Code quality observations (performance, readability, edge cases)
  - For "solved": what they did well, any optimization opportunities
  - For "retry": what's wrong and a nudge toward fixing it (without giving the answer)
  - For "move_on": key takeaways from this problem, what to study

- "next_difficulty": suggestion for next problem difficulty ("easy", "medium", "hard", or null if "retry")
  - If solved easily (few attempts): suggest harder
  - If solved with struggle: suggest same level
  - If move_on: suggest easier"""

    raw = _call_claude(prompt)
    data = _extract_json(raw)
    return SubmissionVerdict(**data)


def generate_scaffold(
    question: str,
    user_code: str,
    role: str,
    category: str,
    history_summary: str,
) -> GeneratedProblem:
    prompt = f"""A student is stuck on this interview problem:

{question}

Their current attempt:
```python
{user_code}
```

Role: {role}
Category: {category}

Generate an EASIER prerequisite problem that teaches the core concept needed to solve the
harder problem above. The easier problem should:
- Focus on the specific concept the student seems to be missing
- Be solvable in isolation
- Build intuition that transfers to the harder problem

Respond ONLY with a JSON block (wrapped in ```json``` markers) with these exact keys:
- "title": short title (string)
- "question": full problem statement in markdown (string)
- "theory": background theory in markdown (string)
- "tests_open": pytest test code importing `from solution import solve` (string)
- "tests_hidden": pytest hidden test code importing `from solution import solve` (string)
- "solution_template": starter code with `def solve(...)` (string)
- "reference_solution": a complete correct solution that passes all tests (string)

Make the difficulty EASY relative to the original problem."""

    raw = _call_claude(prompt)
    data = _extract_json(raw)
    return GeneratedProblem(**data)


def review_derivation(
    question: str,
    user_answer: str,
    reference_solution: str,
    difficulty: str,
    role: str,
    attempts: int,
    chat_history: list[dict] | None = None,
) -> SubmissionVerdict:
    history_text = _format_chat_history(chat_history or [])
    history_section = f"\n\nChat discussion with student:\n{history_text}" if history_text else ""

    prompt = f"""You are reviewing a student's written answer for an interview practice problem.

Problem:
{question}

Student's answer (in markdown):
{user_answer}

Reference solution:
{reference_solution}{history_section}

Context:
- Role: {role}
- Difficulty: {difficulty}
- Attempts: {attempts}

Review the answer and decide what happens next. The student does NOT need to match the
reference solution exactly -- they can use different valid approaches or framings. Judge
correctness, completeness, and quality of reasoning.

For math/derivation problems: judge mathematical correctness and rigor.
For conceptual/behavioral questions: judge depth of understanding, clarity, and completeness.
For puzzles: judge whether they reached the right answer with sound reasoning.

Respond ONLY with a JSON block (wrapped in ```json``` markers) with these exact keys:

- "decision": one of "solved", "retry", or "move_on"
  - "solved": the answer is correct and sufficiently complete
  - "retry": there are significant errors or missing elements worth addressing
  - "move_on": the student has been struggling too long

- "feedback": detailed feedback string. Include:
  - Whether the answer is correct/complete
  - What's strong and what's missing or wrong
  - For "retry": specific guidance toward improving (without giving the full answer)
  - For "move_on": key takeaways

- "next_difficulty": suggestion for next problem difficulty ("easy", "medium", "hard", or null if "retry")"""

    raw = _call_claude(prompt)
    data = _extract_json(raw)
    return SubmissionVerdict(**data)


def generate_derivation_scaffold(
    question: str,
    user_answer: str,
    role: str,
    category: str,
    history_summary: str,
) -> GeneratedDerivation:
    prompt = f"""A student is stuck on this written-answer problem:

{question}

Their current attempt:
{user_answer}

Role: {role}
Category: {category}

Generate an EASIER prerequisite problem that teaches the core concept needed. The easier problem should:
- Focus on the specific concept the student seems to be missing
- Be solvable in isolation
- Build understanding that transfers to the harder problem
- Be the same style (written answer in markdown)

Respond ONLY with a JSON block (wrapped in ```json``` markers) with these exact keys:
- "title": short title (string)
- "question": problem statement in markdown (string)
- "theory": background context in markdown (string)
- "solution_template": markdown starter template with section headings (string)
- "reference_solution": complete answer in markdown (string)

Make the difficulty EASY relative to the original problem."""

    raw = _call_claude(prompt)
    data = _extract_json(raw)
    return GeneratedDerivation(**data)
