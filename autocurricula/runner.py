from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SANDBOX_DIR = Path.home() / "autocurricula" / ".sandbox_venv"

SANDBOX_PACKAGES = [
    "pytest>=7.0.0",
    "numpy",
    "torch",
    "scipy",
    "pandas",
]


@dataclass
class TestResult:
    passed: bool
    output: str
    num_passed: int = 0
    num_failed: int = 0


def _get_sandbox_python() -> str:
    """Return the path to the sandbox venv's Python, creating it if needed."""
    python_path = SANDBOX_DIR / "bin" / "python"
    if python_path.exists():
        return str(python_path)

    subprocess.run(
        [sys.executable, "-m", "venv", str(SANDBOX_DIR)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [str(python_path), "-m", "pip", "install", *SANDBOX_PACKAGES],
        check=True,
        capture_output=True,
    )
    return str(python_path)


def run_tests(problem_dir: str | Path, hidden: bool = False) -> TestResult:
    problem_dir = Path(problem_dir)
    test_file = "tests_hidden.py" if hidden else "tests_open.py"
    test_path = problem_dir / test_file

    if not test_path.exists():
        return TestResult(passed=False, output=f"Test file not found: {test_file}")

    solution_path = problem_dir / "solution.py"
    if not solution_path.exists():
        return TestResult(passed=False, output="solution.py not found. Write your solution first.")

    sandbox_python = _get_sandbox_python()

    result = subprocess.run(
        [sandbox_python, "-m", "pytest", str(test_path), "-v", "--tb=short", "--no-header"],
        capture_output=True,
        text=True,
        cwd=str(problem_dir),
        timeout=30,
    )

    output = result.stdout + result.stderr

    # Count passed/failed from pytest output
    num_passed = output.count(" PASSED")
    num_failed = output.count(" FAILED")

    return TestResult(
        passed=result.returncode == 0,
        output=output,
        num_passed=num_passed,
        num_failed=num_failed,
    )


def run_solution(problem_dir: str | Path) -> TestResult:
    """Run solution.py directly and return its output."""
    problem_dir = Path(problem_dir)
    solution_path = problem_dir / "solution.py"

    if not solution_path.exists():
        return TestResult(passed=False, output="solution.py not found.")

    sandbox_python = _get_sandbox_python()

    result = subprocess.run(
        [sandbox_python, str(solution_path)],
        capture_output=True,
        text=True,
        cwd=str(problem_dir),
        timeout=30,
    )

    output = result.stdout
    if result.stderr:
        output += result.stderr

    return TestResult(
        passed=result.returncode == 0,
        output=output or "",
    )
