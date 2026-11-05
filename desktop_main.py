"""Daily Money Transfer Manager 2026 - Windows desktop launcher.

This is the entry point of the packaged desktop application. It does three
things:

1. starts the existing Streamlit application as a *local* server bound to
   127.0.0.1 on a free port, in a background child process;
2. shows a native Windows window (pywebview / Edge WebView2) with a loading
   screen, then switches it to the application once the server is healthy;
3. shuts the server down again when the window is closed.

The same file is used for the child process: the launcher re-executes itself
with ``--serve`` (see :func:`serve`). Nothing here changes the Streamlit app
itself - ``app.py`` and the ``core``/``ui`` packages run unmodified.

Usage (development):   python desktop_main.py
Usage (packaged):      DailyMoneyTransferManager.exe
Self-test:             DailyMoneyTransferManager.exe --self-test
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Paths and logging (must work before any heavy import)
# --------------------------------------------------------------------------
IS_FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if not IS_FROZEN:
    # Development: make the project importable exactly like ``streamlit run``.
    sys.path.insert(0, str(BUNDLE_DIR))

from config import (  # noqa: E402  (import after sys.path fix)
    APP_TITLE,
    APP_VERSION,
    BACKUP_DIR,
    DATA_DIR,
    DB_PATH,
    EXCEL_EXPORT_DIR,
    IS_PORTABLE,
    LOG_DIR,
    REPORT_EXPORT_DIR,
)

APP_SCRIPT = BUNDLE_DIR / "app.py"
STREAMLIT_CONFIG_DIR = BUNDLE_DIR / ".streamlit"
ICON_PATH = BUNDLE_DIR / "assets" / "icon.ico"
MUTEX_NAME = "Local\\DailyMoneyTransferManager2026.SingleInstance"
HEALTH_TIMEOUT_SECONDS = 90
WINDOW_SIZE = (1366, 860)
WINDOW_MIN_SIZE = (1024, 680)

_LOG_FILE: Path | None = None


def _open_log(name: str) -> Path:
    """Send stdout/stderr to a log file (the packaged app has no console)."""
    global _LOG_FILE
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_FILE = LOG_DIR / name
    handle = open(_LOG_FILE, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None or IS_FROZEN:
        sys.stdout = handle
    if sys.stderr is None or IS_FROZEN:
        sys.stderr = handle
    return _LOG_FILE


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def _message_box(text: str, title: str = APP_TITLE, icon: int = 0x10) -> None:
    """Native Windows message box (icon 0x10 = error, 0x30 = warning, 0x40 = info)."""
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, icon | 0x0)
    except Exception:  # pragma: no cover - non-Windows
        print(f"{title}: {text}", file=sys.stderr)


# --------------------------------------------------------------------------
# Helpers that are easy to unit-test
# --------------------------------------------------------------------------
def find_free_port(host: str = "127.0.0.1") -> int:
    """Ask the OS for a free TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/_stcore/health"


def app_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def server_is_healthy(port: int, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(health_url(port), timeout=timeout) as response:
            return response.status == 200 and response.read().strip().lower() == b"ok"
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_for_server(port: int, process: subprocess.Popen | None, timeout: float = HEALTH_TIMEOUT_SECONDS,
                    interval: float = 0.4) -> bool:
    """Poll the health endpoint until it answers, the process dies, or time runs out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if server_is_healthy(port):
            return True
        time.sleep(interval)
    return False


def webview2_runtime_installed() -> bool:
    """True when the Microsoft Edge WebView2 runtime (or Edge itself) is present."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return False
    client = r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    candidates = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE, client),
        (winreg.HKEY_CURRENT_USER, client),
    ]
    for root, key_path in candidates:
        try:
            with winreg.OpenKey(root, key_path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


class SingleInstance:
    """Named mutex so a second launch shows a notice instead of a second server."""

    def __init__(self, name: str = MUTEX_NAME):
        self.name = name
        self.handle = None
        self.already_running = False

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        kernel32 = ctypes.windll.kernel32
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        self.already_running = kernel32.GetLastError() == 183          # ERROR_ALREADY_EXISTS
        return not self.already_running

    def release(self) -> None:
        if self.handle and sys.platform == "win32":
            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


def ensure_data_folders() -> None:
    for folder in (DATA_DIR, BACKUP_DIR, LOG_DIR, EXCEL_EXPORT_DIR, REPORT_EXPORT_DIR):
        folder.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# HTML shown inside the native window before / instead of the app
# --------------------------------------------------------------------------
def loading_html(message: str = "Starting the local application server...") -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{APP_TITLE}</title>
<style>
 html,body{{height:100%;margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#F4F6FA;color:#1B2430}}
 .wrap{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}}
 .logo{{width:84px;height:84px;border-radius:20px;background:#1F3A5F;display:flex;align-items:center;justify-content:center}}
 .logo span{{color:#fff;font-size:42px;font-weight:700}}
 h1{{font-size:22px;margin:0;font-weight:600}} p{{margin:0;color:#5b6472}}
 .bar{{width:260px;height:6px;border-radius:3px;background:#dde3ec;overflow:hidden}}
 .bar i{{display:block;height:100%;width:40%;background:#1F3A5F;border-radius:3px;animation:slide 1.2s infinite ease-in-out}}
 @keyframes slide{{0%{{transform:translateX(-100%)}}100%{{transform:translateX(350%)}}}}
 small{{color:#8a94a3}}
</style></head><body><div class="wrap">
<div class="logo"><span>$</span></div>
<h1>{APP_TITLE}</h1>
<p id="msg">{message}</p>
<div class="bar"><i></i></div>
<small>Version {APP_VERSION} &middot; data stays on this computer</small>
</div></body></html>"""


def error_html(title: str, detail: str, log_path: Path | None) -> str:
    log_line = f"<p>Details were written to:<br><code>{log_path}</code></p>" if log_path else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{APP_TITLE}</title>
<style>
 body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#F4F6FA;color:#1B2430}}
 .box{{max-width:720px;margin:60px auto;background:#fff;border:1px solid #e3e7ee;border-radius:12px;padding:28px 32px}}
 h1{{font-size:20px;margin:0 0 12px;color:#9a1b1b}} pre{{white-space:pre-wrap;background:#f6f7f9;padding:12px;border-radius:8px;font-size:12px}}
 code{{font-size:12px}}
</style></head><body><div class="box">
<h1>{title}</h1>
<pre>{detail}</pre>
{log_line}
<p>Close this window and start the application again. If the problem persists, send the log file to support.</p>
</div></body></html>"""


# --------------------------------------------------------------------------
# Child process: the Streamlit server
# --------------------------------------------------------------------------
def _watch_parent(parent_pid: int) -> None:
    """Exit the server if the launcher disappears (crash, task-kill, logoff)."""
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x00100000
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
    if not handle:
        return

    def _wait() -> None:
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)          # INFINITE
        log("Launcher process ended - stopping server.")
        os._exit(0)

    threading.Thread(target=_wait, name="parent-watchdog", daemon=True).start()


def serve(port: int, parent_pid: int | None) -> int:
    """Run the Streamlit server in this process (blocking)."""
    _open_log("server.log")
    log(f"Server starting on 127.0.0.1:{port} (pid {os.getpid()}, frozen={IS_FROZEN})")
    log(f"Database: {DB_PATH}")
    if parent_pid:
        _watch_parent(parent_pid)
    # Initialise (or migrate, with a safety backup) the database before the UI
    # can touch it, so first launch and updates are handled deterministically.
    from core.database import Database

    database = Database(DB_PATH)
    log(f"Database ready: {database.count_transactions()} transaction(s), backups in {database.backup_dir}")
    # Streamlit reads ./.streamlit/config.toml relative to the working directory.
    if STREAMLIT_CONFIG_DIR.exists():
        os.chdir(BUNDLE_DIR)
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    from streamlit.web import bootstrap

    flags = {
        "server.address": "127.0.0.1",
        "server.port": port,
        "server.headless": True,
        "server.runOnSave": False,
        "server.fileWatcherType": "none",
        "server.enableStaticServing": False,
        "browser.gatherUsageStats": False,
        "browser.serverAddress": "127.0.0.1",
        "browser.serverPort": port,
        "global.developmentMode": False,
        "client.toolbarMode": "minimal",
    }
    # ``load_config_options`` is what the ``streamlit run`` CLI calls before
    # ``run``; without it the flags are only *watched*, not applied, and the
    # server would fall back to 0.0.0.0:8501.
    bootstrap.load_config_options(flag_options=flags)
    from streamlit import config as st_config
    bound = (st_config.get_option("server.address"), st_config.get_option("server.port"))
    log(f"Effective bind address: {bound[0]}:{bound[1]}")
    if bound != ("127.0.0.1", port):
        raise RuntimeError(f"Refusing to start: server would bind to {bound[0]}:{bound[1]} instead of 127.0.0.1:{port}")
    bootstrap.run(str(APP_SCRIPT), False, [], flags)
    return 0


def start_server_process(port: int) -> subprocess.Popen:
    """Spawn this program again in server mode, hidden, bound to loopback."""
    if IS_FROZEN:
        command = [sys.executable, "--serve", "--port", str(port), "--parent-pid", str(os.getpid())]
    else:
        command = [sys.executable, str(Path(__file__).resolve()), "--serve", "--port", str(port),
                   "--parent-pid", str(os.getpid())]
    creation_flags = 0
    startupinfo = None
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(command, creationflags=creation_flags, startupinfo=startupinfo, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            close_fds=True)


def stop_server_process(process: subprocess.Popen | None, grace: float = 6.0) -> None:
    if process is None or process.poll() is not None:
        return
    log("Stopping server process...")
    try:
        process.terminate()
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        log("Server did not stop in time - killing it.")
        process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    except Exception as exc:  # pragma: no cover
        log(f"Error while stopping server: {exc}")
    log("Server stopped.")


# --------------------------------------------------------------------------
# Parent process: native window
# --------------------------------------------------------------------------
def run_desktop(self_test: bool = False, self_test_seconds: float = 20.0) -> int:
    log_path = _open_log("launcher.log")
    log(f"{APP_TITLE} v{APP_VERSION} starting (frozen={IS_FROZEN}, portable={IS_PORTABLE})")
    log(f"Data folder: {DATA_DIR}")
    ensure_data_folders()

    instance = SingleInstance()
    if not instance.acquire():
        log("Another instance is already running - exiting.")
        _message_box(f"{APP_TITLE} is already running.\n\nLook for its window on the taskbar.",
                     icon=0x40)
        return 3

    if sys.platform == "win32" and not webview2_runtime_installed():
        log("WebView2 runtime not found.")
        _message_box(
            "The Microsoft Edge WebView2 Runtime is required to display the application window.\n\n"
            "It is included with Windows 11 and recent Windows 10 updates. If this message appears, "
            "install it from:\nhttps://developer.microsoft.com/microsoft-edge/webview2/\n\n"
            "Then start the application again.",
            icon=0x30,
        )
        instance.release()
        return 4

    try:
        import webview
    except Exception as exc:  # pragma: no cover - packaging problem
        log(f"pywebview import failed: {exc}")
        _message_box(f"The desktop window component could not be loaded:\n{exc}\n\nLog: {log_path}")
        instance.release()
        return 5

    port = find_free_port()
    log(f"Using port {port}")
    server: subprocess.Popen | None = None
    outcome = {"ready": False, "error": None, "title": None}

    window = webview.create_window(
        APP_TITLE,
        html=loading_html(),
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
        resizable=True,
        text_select=True,
        confirm_close=False,
    )

    def _bootstrap() -> None:
        nonlocal server
        try:
            server = start_server_process(port)
            log(f"Server process pid {server.pid}")
            if wait_for_server(port, server):
                outcome["ready"] = True
                log("Server healthy - loading application.")
                window.load_url(app_url(port))
            else:
                code = server.poll()
                detail = (f"The local server stopped unexpectedly (exit code {code})."
                          if code is not None else
                          f"The local server did not answer within {HEALTH_TIMEOUT_SECONDS} seconds.")
                outcome["error"] = detail
                log(detail)
                window.load_html(error_html("The application could not start", detail,
                                            LOG_DIR / "server.log"))
        except Exception as exc:
            outcome["error"] = f"{exc}\n{traceback.format_exc()}"
            log(outcome["error"])
            window.load_html(error_html("The application could not start", str(exc), log_path))

        if self_test:
            # Give the page time to render, record what the window shows, then close.
            time.sleep(self_test_seconds)
            try:
                outcome["title"] = window.evaluate_js("document.title")
                outcome["body_chars"] = window.evaluate_js("document.body.innerText.length")
            except Exception as exc:  # pragma: no cover
                outcome["title"] = f"evaluate_js failed: {exc}"
            log(f"Self-test window title: {outcome['title']!r}, body chars: {outcome.get('body_chars')}")
            window.destroy()

    storage = DATA_DIR / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(_bootstrap, gui="edgechromium", private_mode=False, storage_path=str(storage),
                      icon=str(ICON_PATH) if ICON_PATH.exists() else None)
    except Exception as exc:
        log(f"Window failed: {exc}\n{traceback.format_exc()}")
        _message_box(f"The application window could not be opened:\n{exc}\n\nLog: {log_path}")
        stop_server_process(server)
        instance.release()
        return 6

    # webview.start() returns once the window is closed.
    stop_server_process(server)
    instance.release()
    log("Application closed.")

    if self_test:
        report = {
            "ready": outcome["ready"],
            "error": outcome["error"],
            "title": outcome["title"],
            "body_chars": outcome.get("body_chars"),
            "server_stopped": server is None or server.poll() is not None,
            "port": port,
            "data_dir": str(DATA_DIR),
            "db_path": str(DB_PATH),
            "log": str(log_path),
        }
        (LOG_DIR / "self-test.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        log(f"Self-test report: {report}")
        ok = report["ready"] and report["server_stopped"] and not report["error"]
        return 0 if ok else 1
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="DailyMoneyTransferManager", add_help=True)
    parser.add_argument("--serve", action="store_true", help="internal: run the local server")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--parent-pid", type=int, default=None)
    parser.add_argument("--self-test", action="store_true",
                        help="start, wait for the window to load, then close and report")
    parser.add_argument("--self-test-seconds", type=float, default=20.0)
    parser.add_argument("--version", action="version", version=f"{APP_TITLE} {APP_VERSION}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.serve:
        if args.port is None:
            raise SystemExit("--serve requires --port")
        return serve(args.port, args.parent_pid)
    return run_desktop(self_test=args.self_test, self_test_seconds=args.self_test_seconds)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # last-resort handler: never die silently in a windowed app
        try:
            _open_log("launcher.log")
            log(f"Fatal error: {exc}\n{traceback.format_exc()}")
        finally:
            _message_box(f"Unexpected error:\n{exc}\n\nLog folder: {LOG_DIR}")
        sys.exit(1)
