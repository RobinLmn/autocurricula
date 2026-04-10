from __future__ import annotations

import asyncio
import re as _re
import time as _time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

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


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)

_boot_version = str(int(_time.time()))


@app.get("/static/js/{filename:path}")
async def serve_js(filename: str):
    """Serve JS files with cache-busted module imports."""
    filepath = STATIC_DIR / "js" / filename
    if not filepath.resolve().is_relative_to((STATIC_DIR / "js").resolve()):
        from starlette.responses import Response

        return Response(status_code=404)
    if not filepath.exists():
        from starlette.responses import Response

        return Response(status_code=404)
    content = filepath.read_text()
    # Rewrite relative ES module imports to bust cache
    content = _re.sub(
        r"""(from\s+['"]\..*?)(\.js)(['"])""",
        rf"\1.js?v={_boot_version}\3",
        content,
    )
    from starlette.responses import Response

    return Response(
        content=content,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    import time

    html = (STATIC_DIR / "index.html").read_text()
    # Bust browser module cache by appending version to JS/CSS imports
    v = str(int(time.time()))
    html = html.replace('.css"', f'.css?v={v}"').replace('.js"', f'.js?v={v}"')
    from starlette.responses import HTMLResponse

    return HTMLResponse(html)


_initial_role: str | None = None


_shutdown_task: asyncio.Task | None = None


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _shutdown_task
    if _shutdown_task is not None:
        _shutdown_task.cancel()
        _shutdown_task = None
    await ws.accept()
    handler = SessionHandler(ws, role=_initial_role)
    await handler.run()
    # Client disconnected — schedule shutdown after grace period for refreshes
    _shutdown_task = asyncio.create_task(_delayed_shutdown(3.0))


async def _delayed_shutdown(delay: float) -> None:
    await asyncio.sleep(delay)
    import os
    import signal

    os.kill(os.getpid(), signal.SIGINT)


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


def _check_for_update() -> None:
    """Check PyPI for a newer version and offer to upgrade."""
    import subprocess
    import sys
    from importlib.metadata import version as pkg_version
    from urllib.request import urlopen

    try:
        current = pkg_version("autocurricula")
        with urlopen("https://pypi.org/pypi/autocurricula/json", timeout=3) as resp:
            import json

            latest = json.loads(resp.read())["info"]["version"]
        from packaging.version import Version

        if Version(current) >= Version(latest):
            return
        answer = input(f"Update available: {current} → {latest}. Update now? [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "autocurricula"])
            print(f"Updated to {latest}. Please re-run autocurricula.")
            sys.exit(0)
    except Exception:
        pass


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Adaptive interview practice")
    parser.add_argument("-p", "--port", type=int, default=8420, help="Port for web server (default: 8420)")
    args = parser.parse_args()

    _check_for_update()
    run_server(port=args.port)
