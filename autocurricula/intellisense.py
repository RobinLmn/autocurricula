from __future__ import annotations

import jedi

from .runner import SANDBOX_DIR

DOC_URLS: dict[str, str] = {
    "numpy": "https://numpy.org/doc/stable/reference/generated/{name}.html",
    "pandas": "https://pandas.pydata.org/docs/reference/api/{name}.html",
    "scipy": "https://docs.scipy.org/doc/scipy/reference/generated/{name}.html",
    "torch": "https://pytorch.org/docs/stable/generated/{name}.html",
}

# Internal submodule prefixes to strip for public doc URLs
_NUMPY_INTERNAL = (
    "numpy.core.fromnumeric.",
    "numpy.core.multiarray.",
    "numpy.core.numeric.",
    "numpy.core.function_base.",
    "numpy.core._methods.",
    "numpy.lib.function_base.",
    "numpy.lib.nanfunctions.",
    "numpy.lib.shape_base.",
    "numpy.lib.arraysetops.",
    "numpy.linalg.linalg.",
    "numpy.random.mtrand.",
    "numpy._core.fromnumeric.",
    "numpy._core.multiarray.",
    "numpy._core.numeric.",
    "numpy._core.function_base.",
    "numpy._core._methods.",
)


def _public_name(full_name: str | None) -> str | None:
    """Convert an internal module path to its public API name."""
    if not full_name:
        return None
    # numpy internal -> numpy.X
    for prefix in _NUMPY_INTERNAL:
        if full_name.startswith(prefix):
            return "numpy." + full_name[len(prefix):]
    # torch.nn.modules.X.Y -> torch.nn.Y
    if full_name.startswith("torch.nn.modules."):
        parts = full_name.split(".")
        return "torch.nn." + parts[-1]
    return full_name


_PYTHON_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "breakpoint", "bytearray",
    "bytes", "callable", "chr", "classmethod", "compile", "complex",
    "delattr", "dict", "dir", "divmod", "enumerate", "eval", "exec",
    "filter", "float", "format", "frozenset", "getattr", "globals",
    "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance",
    "issubclass", "iter", "len", "list", "locals", "map", "max",
    "memoryview", "min", "next", "object", "oct", "open", "ord", "pow",
    "print", "property", "range", "repr", "reversed", "round", "set",
    "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super",
    "tuple", "type", "vars", "zip",
}


def get_doc_url(full_name: str | None) -> str | None:
    """Return a documentation URL for a known library symbol, or None."""
    name = _public_name(full_name)
    if not name:
        return None
    for lib, pattern in DOC_URLS.items():
        if name.startswith(lib + "."):
            return pattern.format(name=name)
    # Python builtins
    if name.startswith("builtins."):
        short = name.split(".")[-1]
        if short in _PYTHON_BUILTINS:
            return f"https://docs.python.org/3/library/functions.html#{short}"
    # Python stdlib modules (e.g. collections.Counter, itertools.chain)
    parts = name.split(".")
    if len(parts) >= 2 and parts[0] in (
        "collections", "itertools", "functools", "math", "statistics",
        "heapq", "bisect", "operator", "re", "json", "os", "sys",
        "typing", "dataclasses", "datetime", "random", "string",
    ):
        return f"https://docs.python.org/3/library/{parts[0]}.html#{name}"
    return None


_sandbox_sys_path: list[str] | None = None


def _get_sandbox_sys_path() -> list[str]:
    global _sandbox_sys_path
    if _sandbox_sys_path is not None:
        return _sandbox_sys_path
    site_pkgs = list(SANDBOX_DIR.glob("lib/python*/site-packages"))
    _sandbox_sys_path = [str(p) for p in site_pkgs]
    return _sandbox_sys_path


def _script(source: str) -> jedi.Script:
    env = None
    sandbox_python = SANDBOX_DIR / "bin" / "python"
    if sandbox_python.exists():
        try:
            env = jedi.get_default_environment()
        except Exception:
            pass

    project = jedi.Project(
        path=".",
        added_sys_path=_get_sandbox_sys_path(),
    )
    return jedi.Script(
        source,
        path="solution.py",
        project=project,
        environment=env,
    )


KIND_MAP = {
    "module": "Module",
    "class": "Class",
    "instance": "Variable",
    "function": "Function",
    "param": "Variable",
    "path": "File",
    "keyword": "Keyword",
    "property": "Property",
    "statement": "Variable",
}


def get_completions(source: str, line: int, column: int) -> list[dict]:
    """line is 1-indexed, column is 1-indexed (Monaco convention). Jedi uses 0-indexed columns."""
    try:
        completions = _script(source).complete(line, column - 1)
    except Exception:
        return []

    results = []
    for c in completions[:40]:  # cap at 40
        try:
            sigs = c.get_signatures()
            detail = str(sigs[0]) if sigs else (c.description or "")
        except Exception:
            detail = c.description or ""

        doc = ""
        doc_url = None
        try:
            doc = c.docstring(raw=True) or ""
            doc_url = get_doc_url(c.full_name)
        except Exception:
            pass

        results.append({
            "name": c.name,
            "kind": KIND_MAP.get(c.type, "Variable"),
            "detail": detail,
            "doc": doc[:500] if doc else "",
            "doc_url": doc_url,
        })
    return results


def get_hover(source: str, line: int, column: int) -> dict | None:
    """line and column are 1-indexed (Monaco convention)."""
    try:
        names = _script(source).help(line, column - 1)
        if not names:
            return None
        n = names[0]
        sigs = n.get_signatures()
        sig_str = str(sigs[0]) if sigs else ""
        doc = n.docstring(raw=True) or ""
        doc_url = get_doc_url(n.full_name)
        return {
            "name": n.name,
            "signature": sig_str,
            "doc": doc[:2000],
            "doc_url": doc_url,
        }
    except Exception:
        return None


def get_signatures(source: str, line: int, column: int) -> list[dict]:
    """line and column are 1-indexed (Monaco convention)."""
    try:
        sigs = _script(source).get_signatures(line, column - 1)
    except Exception:
        return []

    results = []
    for s in sigs:
        params = []
        for p in s.params:
            params.append({
                "name": p.name,
                "description": p.description,
            })
        doc_url = get_doc_url(s.full_name)
        results.append({
            "name": s.name,
            "params": params,
            "index": s.index if s.index is not None else 0,
            "doc": (s.docstring(raw=True) or "")[:500],
            "doc_url": doc_url,
        })
    return results
