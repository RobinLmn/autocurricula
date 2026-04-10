# autocurricula [![CI](https://github.com/RobinLmn/autocurricula/actions/workflows/ci.yml/badge.svg)](https://github.com/RobinLmn/autocurricula/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/) [![PyPI](https://img.shields.io/pypi/v/autocurricula.svg)](https://pypi.org/project/autocurricula/) [![Website](https://img.shields.io/badge/Website-robinlmn.github.io-green)](https://robinlmn.github.io/autocurricula/)

Adaptive technical interview practice, powered by Claude. Problems are generated on-the-fly based on your role and skill level, with real-time code execution, structured test results, and AI-driven feedback.

Covers coding, algorithms, math, probability, statistics, and brainteasers.

## Installation

```bash
pip install autocurricula
```

**Prerequisites:** [Claude CLI](https://claude.ai/download) must be installed and authenticated.

## Quick start

```bash
autocurricula
```

This opens the app in your browser at `http://localhost:8420`.

On first launch, create a workspace by choosing a role (e.g. "ML Engineer", "Quant Researcher", "Backend Developer"). Claude generates problems tailored to that role and adapts difficulty as you progress.

> A sandboxed virtual environment is automatically created at `~/.autocurricula/.sandbox_venv` with numpy, pandas, scipy, torch, and pytest for executing solutions.

## How it works

**autocurricula** uses a self-adjusting curriculum loop:

1. Claude generates a problem matched to your role, category, and current difficulty level.
2. You solve it in the built-in editor with full autocompletion and live test feedback.
3. Claude reviews your submission, gives a verdict (solved / retry / move on), and explains the reasoning.
4. The system tracks your solve rate and self-rated difficulty to calibrate what comes next.

Categories rotate automatically to ensure broad coverage.

## Features

### Problem types

| Type | Description |
|------|-------------|
| **Code** | Write a function, run open tests, then submit for hidden tests and Claude review. |
| **Derivation** | Written answers for math proofs, probability puzzles, system design reasoning, and conceptual questions. |

### Code editor

Monaco editor with Python syntax highlighting, autocompletion, hover documentation, and function signatures powered by [Jedi](https://github.com/davidhalter/jedi). Supports numpy, pandas, scipy, and torch out of the box.

### Test runner

Each code problem includes an open test suite (visible while solving) and a hidden test suite (run on submit). Tests execute in an isolated sandbox with a 30-second timeout. Results show structured pass/fail/error status with expandable failure details.

### Scaffolding

Stuck? Request a scaffold and Claude generates an easier prerequisite targeting the specific concept you're missing. Solve it, then return to the original problem.

### Theory

Each problem comes with background material covering relevant formulas, derivations, algorithmic intuitions, and worked examples. Rendered with LaTeX support.

### Chat

Ask Claude for hints without getting the answer. Claude sees your current code and problem statement for context. Chat history is preserved per problem.

### Progress tracking

Track solve counts, attempt counts, and success rates across all categories. Rate each solved problem's difficulty (1–5) to help the system calibrate. Problems solved but rated as hard are flagged for revisiting.

### Workspaces

Maintain separate workspaces for different roles, each with its own problem history, progress state, and difficulty curve.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--port`, `-p` | `8420` | Port for the web server |

## License

[MIT](LICENSE) — free to use, modify, and distribute.
