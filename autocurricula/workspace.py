from __future__ import annotations

import re
from pathlib import Path

DATA_DIR = Path.home() / "autocurricula"
WORKSPACES_DIR = DATA_DIR / "workspaces"
CONFIG_FILE = DATA_DIR / ".workspace"


def _slugify(role: str) -> str:
    slug = role.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def list_workspaces() -> dict[str, str]:
    """Return {slug: role_name} for all existing workspaces."""
    result: dict[str, str] = {}
    if not WORKSPACES_DIR.exists():
        return result
    for d in sorted(WORKSPACES_DIR.iterdir()):
        if d.is_dir():
            role_file = d / ".role"
            if role_file.exists():
                result[d.name] = role_file.read_text().strip()
    return result


def get_last_workspace() -> str | None:
    """Return the slug of the last used workspace, or None."""
    if CONFIG_FILE.exists():
        return CONFIG_FILE.read_text().strip() or None
    return None


def init_workspace(role: str | None = None) -> tuple[str, Path] | None:
    """Initialize a workspace for the given role. Returns (role, workspace_dir).

    If role is None, reopens the last used workspace.
    Returns None if no workspace exists and no role given (needs onboarding).
    """
    if role is None:
        last = get_last_workspace()
        if last:
            ws_dir = WORKSPACES_DIR / last
            role_file = ws_dir / ".role"
            if role_file.exists():
                return role_file.read_text().strip(), ws_dir
        # No last workspace -- check if any exist
        workspaces = list_workspaces()
        if not workspaces:
            return None  # Needs onboarding
        # Pick the first one
        slug = next(iter(workspaces))
        ws_dir = WORKSPACES_DIR / slug
        return workspaces[slug], ws_dir

    return create_workspace(role)


def create_workspace(role: str, description: str = "") -> tuple[str, Path]:
    """Create (or reopen) a workspace for the given role. Returns (role, workspace_dir)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slugify(role)
    ws_dir = WORKSPACES_DIR / slug
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "problems").mkdir(exist_ok=True)
    (ws_dir / ".role").write_text(role)
    if description:
        (ws_dir / ".description").write_text(description)

    CONFIG_FILE.write_text(slug)

    return role, ws_dir


def get_description(workspace_dir: Path) -> str:
    """Return the user's original role description, or empty string."""
    desc_file = workspace_dir / ".description"
    return desc_file.read_text().strip() if desc_file.exists() else ""


def get_problems_dir(workspace_dir: Path) -> Path:
    return workspace_dir / "problems"


def get_progress_file(workspace_dir: Path) -> Path:
    return workspace_dir / "progress.json"
