from __future__ import annotations

import webbrowser
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .session_handler import SessionHandler
from .workspace import WORKSPACES_DIR

STATIC_DIR = Path(__file__).parent / "static"


def _safe_workspace_path(slug: str) -> Path | None:
    """Resolve a workspace slug and ensure it stays within WORKSPACES_DIR."""
    resolved = (WORKSPACES_DIR / slug).resolve()
    if not resolved.is_relative_to(WORKSPACES_DIR.resolve()):
        return None
    return resolved


def _safe_subpath(base: Path, untrusted: str) -> Path | None:
    """Resolve an untrusted path component and ensure it stays within base."""
    resolved = (base / untrusted).resolve()
    if not resolved.is_relative_to(base.resolve()):
        return None
    return resolved


app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


_initial_role: str | None = None


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    handler = SessionHandler(ws, role=_initial_role)
    await handler.run()


def run_server(role: str | None = None, port: int = 8420) -> None:
    global _initial_role
    _initial_role = role

    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, 10240), hard))
    except (ModuleNotFoundError, ValueError, OSError):
        pass

    import uvicorn

    url = f"http://localhost:{port}"
    print(f"autocurricula \u2192 {url}")

    import threading

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Adaptive interview practice")
    parser.add_argument("-p", "--port", type=int, default=8420, help="Port for web server (default: 8420)")
    args = parser.parse_args()

    run_server(port=args.port)
