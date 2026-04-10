from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import GeneratedContent, GeneratedDerivation, GeneratedProblem, SubmissionVerdict


@dataclass
class ClaudeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost_usd: float = 0.0

    @classmethod
    def from_json(cls, data: dict) -> "ClaudeUsage":
        usage = data.get("usage", {})
        return cls(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
            cost_usd=data.get("total_cost_usd", 0.0),
        )

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens + self.cache_read_input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
        }


@dataclass
class GenerationProgress:
    """Accumulates token usage across multiple Claude calls during generation."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    def add_usage(self, data: dict) -> None:
        """Add usage from a to_dict()-style dict (with input_tokens, output_tokens, cost_usd)."""
        self.total_input_tokens += data.get("input_tokens", 0)
        self.total_output_tokens += data.get("output_tokens", 0)
        self.total_cost_usd += data.get("cost_usd", 0.0)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.total_cost_usd, 4),
        }


_USAGE_LOG: Path | None = None


def _get_usage_log() -> Path:
    global _USAGE_LOG
    if _USAGE_LOG is None:
        from .workspace import DATA_DIR
        _USAGE_LOG = DATA_DIR / "token_usage.jsonl"
    return _USAGE_LOG


def _log_usage(usage: ClaudeUsage) -> None:
    """Append a usage record to the global JSONL log."""
    path = _get_usage_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(),
        "input_tokens": usage.input_tokens + usage.cache_read_input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": usage.cost_usd,
    }
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def get_usage_last_24h() -> dict:
    """Return aggregated token usage from the last 24 hours."""
    path = _get_usage_log()
    cutoff = time.time() - 86400
    total_input = 0
    total_output = 0
    total_cost = 0.0
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if rec.get("ts", 0) >= cutoff:
                    total_input += rec.get("input_tokens", 0)
                    total_output += rec.get("output_tokens", 0)
                    total_cost += rec.get("cost_usd", 0.0)
    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "cost_usd": round(total_cost, 4),
    }


def _call_claude(
    prompt: str,
    on_progress: ProgressCallback = None,
    step: str = "",
) -> tuple[str, ClaudeUsage]:
    """Call Claude CLI with streaming to get real-time token updates.

    When on_progress is provided, fires a '{step}_tokens' callback as soon as
    the assistant event arrives (before the final result).
    """
    proc = subprocess.Popen(
        ["claude", "-p", "--verbose", "--output-format", "stream-json", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    usage = ClaudeUsage()
    text = ""
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            etype = event.get("type", "")
            if etype == "assistant" and on_progress and step:
                # Token counts available as soon as model finishes generating
                msg = event.get("message", {})
                msg_usage = msg.get("usage", {})
                early = ClaudeUsage(
                    input_tokens=msg_usage.get("input_tokens", 0),
                    output_tokens=msg_usage.get("output_tokens", 0),
                    cache_read_input_tokens=msg_usage.get("cache_read_input_tokens", 0),
                )
                on_progress(f"{step}_tokens", early.to_dict())
            elif etype == "result":
                usage = ClaudeUsage.from_json(event)
                text = event.get("result", "").strip()
    except Exception:
        pass
    proc.wait(timeout=120)
    if proc.returncode != 0:
        stderr = proc.stderr.read() if proc.stderr else ""  # type: ignore[union-attr]
        raise RuntimeError(f"Claude call failed: {stderr}")
    _log_usage(usage)
    return text, usage


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

    text, _ = _call_claude(prompt)
    return text


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
    text, _ = _call_claude(prompt)
    return text


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        result: dict[str, Any] = json.loads(match.group(1))
        return result
    result = json.loads(text)
    return result


ProgressCallback = Any  # Callable[[str, dict], None] | None


def generate_next_problem(
    role: str,
    description: str,
    history_summary: str,
    user_prompt: str = "",
    on_progress: ProgressCallback = None,
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
- **Breadth first**: prioritize tags and topics the student hasn't covered yet. \
For coding, rotate across data structures (array, string, tree, graph, linked-list, stack, queue, heap) \
and techniques (dynamic-programming, greedy, sliding-window, two-pointers, bfs, dfs, \
binary-search, backtracking, sorting). \
Check the "Tags covered so far" section and pick under-represented tags.
- Which categories they've under-practiced or struggled with
- Whether to escalate, maintain, or reduce difficulty
- Whether a coding problem ("python") or written-answer problem ("markdown") fits best
- Avoid repeating recent categories or tags unless the student needs more practice there

Respond ONLY with a JSON block (wrapped in ```json``` markers) with these keys:

- "title": short descriptive title (string)
- "category": lowercase category label, e.g. "algorithms", "probability", "ml", "system design" (string)
- "tags": 2-4 specific topic tags describing the core techniques and data structures involved, \
e.g. ["array", "sliding-window"], ["tree", "bfs"], ["dynamic-programming", "memoization"], \
["string", "two-pointers"], ["graph", "shortest-path"], ["probability", "bayes-theorem"]. \
Use consistent lowercase kebab-case names. (list of strings)
- "difficulty": "easy", "medium", or "hard" (string)
- "format": "python" or "markdown" (string)
- "question": full problem statement in markdown. Write it like a real interview question. \
For python: state WHAT to implement, specify inputs/outputs and types, give 1-2 examples. \
For markdown: be specific about what to address, use LaTeX ($...$) for math. \
Do NOT include implementation hints. (string)
- "theory": background theory in markdown covering the underlying concepts and data structures, \
NOT applied to this specific problem. For example, for a graph traversal problem, explain what DFS/BFS are \
and how they work in general — do NOT explain how to use them to solve this particular problem. \
The student should read the theory to learn the building blocks, then figure out how to apply them. \
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
- If the problem uses custom classes (e.g. TreeNode, ListNode), always include `__repr__` so test output is readable
- Tests should compare primitive values (ints, strings, lists) whenever possible, not object references
- Make sure tests are self-contained and correct"""

    if user_prompt:
        prompt += f'\n\nThe student specifically requested: "{user_prompt}". \
Incorporate this into your problem choice while still following all the rules above.'

    if on_progress:
        on_progress("generating", {})
    raw, usage = _call_claude(prompt, on_progress=on_progress, step="generating")
    if on_progress:
        on_progress("generated", usage.to_dict())
    data = _extract_json(raw)
    return GeneratedContent(**data)


def fix_problem(
    generated: GeneratedProblem,
    test_output: str,
    on_progress: ProgressCallback = None,
) -> GeneratedProblem:
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

    if on_progress:
        on_progress("fixing", {})
    raw, usage = _call_claude(prompt, on_progress=on_progress, step="fixing")
    if on_progress:
        on_progress("fixed", usage.to_dict())
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
    history_section = f"\n\nYour conversation with the student so far:\n{history_text}" if history_text else ""

    prompt = f"""You are a tutor helping a student practice for technical interviews. \
The student just submitted their solution. Review it and respond directly to them \
(use "you", not "the student").{history_section}

Problem:
{question}

Their solution:
```python
{user_code}
```

Test results (all tests passed: {all_tests_passed}):
{test_output}

Context:
- Role: {role}
- Difficulty: {difficulty}
- Attempts: {attempts}

Decide what happens next. Respond ONLY with a JSON block
(wrapped in ```json``` markers) with these exact keys:

- "decision": one of "solved", "follow_up", "retry", or "move_on"
  - "solved": the solution is correct, all tests pass, and you have no follow-up questions.
  - "follow_up": all tests pass and the solution works, but you want to ask a follow-up question \
before marking it as solved — just like a real interviewer would. Use this to ask about time/space \
complexity, potential optimizations, edge cases, alternative approaches, or trade-offs. \
Use your judgement: not every correct solution needs a follow-up. Simple/easy problems or solutions \
that already demonstrate strong understanding can go straight to "solved".
  - "retry": tests failed or the solution has issues worth fixing. Encourage them to try again.
  - "move_on": the student has been struggling too long (many attempts) and should move to a
    different problem. Mark as unsolved.

- "feedback": detailed feedback string addressing the student directly. Include:
  - Whether the solution is correct
  - Code quality observations (performance, readability, edge cases)
  - For "solved": what they did well
  - For "follow_up": acknowledge the solution works, then ask your follow-up question
  - For "retry": what's wrong and a nudge toward fixing it (without giving the answer)
  - For "move_on": key takeaways from this problem, what to study

- "next_difficulty": suggestion for next problem difficulty ("easy", "medium", "hard", or null if "retry"/"follow_up")
  - If solved easily (few attempts): suggest harder
  - If solved with struggle: suggest same level
  - If move_on: suggest easier"""

    raw, _ = _call_claude(prompt)
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

    raw, _ = _call_claude(prompt)
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
    history_section = f"\n\nYour conversation with the student so far:\n{history_text}" if history_text else ""

    prompt = f"""You are a tutor helping a student practice for technical interviews. \
The student just submitted their written answer. Review it and respond directly to them \
(use "you", not "the student").{history_section}

Problem:
{question}

Their answer (in markdown):
{user_answer}

Reference solution:
{reference_solution}

Context:
- Role: {role}
- Difficulty: {difficulty}
- Attempts: {attempts}

Review the answer and decide what happens next. They do NOT need to match the
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

- "feedback": detailed feedback string addressing the student directly. Include:
  - Whether the answer is correct/complete
  - What's strong and what's missing or wrong
  - For "retry": specific guidance toward improving (without giving the full answer)
  - For "move_on": key takeaways

- "next_difficulty": suggestion for next problem difficulty ("easy", "medium", "hard", or null if "retry")"""

    raw, _ = _call_claude(prompt)
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

    raw, _ = _call_claude(prompt)
    data = _extract_json(raw)
    return GeneratedDerivation(**data)
