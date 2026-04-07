from __future__ import annotations

import re


def parse_pytest_output(output: str) -> list[dict]:
    """Parse pytest -v output into structured test results."""
    tests = []
    pattern = re.compile(r"^(.+?)\s+(PASSED|FAILED|ERROR)\s*(\[.*\])?\s*$")
    for line in output.splitlines():
        m = pattern.match(line.strip())
        if m:
            name = m.group(1).strip()
            result = m.group(2)
            if "::" in name:
                name = name.split("::", 1)[1]
            status = "passed" if result == "PASSED" else ("error" if result == "ERROR" else "failed")
            tests.append({"name": name, "status": status})
    return tests


def extract_failure_details(output: str) -> dict[str, str]:
    """Extract per-test failure details from pytest output."""
    raw_details: dict[str, list[str]] = {}
    current_test = None
    current_lines: list[str] = []

    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("_") and stripped.endswith("_") and len(stripped) > 4:
            if current_test and current_lines:
                raw_details[current_test] = current_lines
            name = stripped.strip("_ ").strip()
            if "::" in name:
                name = name.split("::", 1)[1]
            current_test = name
            current_lines = []
        elif stripped.startswith("FAILED "):
            if current_test and current_lines:
                raw_details[current_test] = current_lines
            current_test = None
            current_lines = []
        elif stripped.startswith("=") and (
            "short test summary" in stripped.lower() or "passed" in stripped.lower() or "failed" in stripped.lower()
        ):
            if current_test and current_lines:
                raw_details[current_test] = current_lines
            current_test = None
            current_lines = []
        elif current_test:
            current_lines.append(line)

    if current_test and current_lines:
        raw_details[current_test] = current_lines

    details: dict[str, str] = {}
    for name, lines in raw_details.items():
        details[name] = _format_failure(lines)
    return details


def _format_failure(lines: list[str]) -> str:
    """Turn a raw pytest failure block into a clean Expected/Got or error summary."""
    text = "\n".join(lines)

    e_assert_eq = re.search(r"^E\s+assert\s+(.+?)\s*==\s*(.+?)$", text, re.MULTILINE)
    if e_assert_eq:
        got, expected = e_assert_eq.group(1).strip(), e_assert_eq.group(2).strip()
        return f"Expected: {expected}\nGot: {got}"

    abs_match = re.search(r"assert\s+abs\((.+?)\)\s*<\s*(.+?)$", text, re.MULTILINE)
    if abs_match:
        where_lines = [ln.strip() for ln in lines if "+  where" in ln or "+ where" in ln]
        for wl in where_lines:
            val_match = re.search(r"abs\([\(\[]?(.+?)\s*-\s*(.+?)\)", wl)
            if val_match:
                got_val = val_match.group(1).strip()
                expected_val = val_match.group(2).strip()
                got_val = re.sub(r"^\w+\.\w+\((.+)\)$", r"\1", got_val)
                return f"Expected: ~{expected_val}\nGot: {got_val}"
        return f"Assertion failed: abs({abs_match.group(1)}) < {abs_match.group(2)}"

    assert_match = re.search(r"assert\s+(.+?)$", text, re.MULTILINE)
    if assert_match:
        assertion = assert_match.group(1).strip()
        where_lines = [ln.strip() for ln in lines if "+  where" in ln or "+ where" in ln]
        if where_lines:
            vals = []
            for wl in where_lines:
                wval = re.search(r"where\s+(.+?)\s*=\s*(.+)", wl)
                if wval:
                    vals.append(f"{wval.group(2).strip()} = {wval.group(1).strip()}")
            if vals:
                return f"Assertion failed: {assertion}\n" + "\n".join(vals)
        return f"Assertion failed: {assertion}"

    err_match = re.search(r"^E\s+(\w*Error\b.*?)$", text, re.MULTILINE)
    if err_match:
        return err_match.group(1).strip()

    e_lines = [ln.strip().lstrip("E").strip() for ln in lines if ln.strip().startswith("E ")]
    if e_lines:
        return "\n".join(e_lines)

    for ln in lines:
        s = ln.strip()
        if s and not s.startswith(">") and ".py:" not in s:
            return s
    return "Test failed"
