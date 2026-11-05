"""Smoke-test a packaged build without a display.

Starts the bundled executable in server mode (the same code path the desktop
window uses), waits for the health endpoint, requests every page of the app
over HTTP and checks that the Streamlit front-end is served, then stops the
process and verifies it is gone. The server must be reachable on 127.0.0.1
only. Exit code 0 means success.

Usage:  python tools/smoke_test_bundle.py dist/DailyMoneyTransferManager/DailyMoneyTransferManager.exe
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PAGES = ["", "dashboard", "upload", "transactions", "daily-summary", "reports", "settings"]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    exe = Path(sys.argv[1]).resolve()
    if not exe.exists():
        print(f"not found: {exe}")
        return 2
    port = free_port()
    data_dir = Path(tempfile.mkdtemp(prefix="dmtm-smoke-"))
    env = dict(os.environ, DMTM_DATA_DIR=str(data_dir))
    print(f"starting {exe.name} --serve --port {port} (data: {data_dir})")
    proc = subprocess.Popen([str(exe), "--serve", "--port", str(port)], env=env)
    ok = True
    try:
        deadline = time.monotonic() + 120
        healthy = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                print(f"server exited early with code {proc.returncode}")
                break
            status, body = get(f"http://127.0.0.1:{port}/_stcore/health", timeout=2)
            if status == 200 and body.strip() == b"ok":
                healthy = True
                break
            time.sleep(0.5)
        print(f"health: {'ok' if healthy else 'FAILED'}")
        ok &= healthy

        if healthy:
            for page in PAGES:
                status, body = get(f"http://127.0.0.1:{port}/{page}")
                served = status == 200 and b"<div id=\"root\">" in body
                print(f"GET /{page:<14} -> {status} {'streamlit page' if served else 'UNEXPECTED'}")
                ok &= served
            # the database must have been created in the data folder, not next to the exe
            db = data_dir / "database.db"
            print(f"database created in data folder: {db.exists()}")
            ok &= db.exists()
            log = data_dir / "logs" / "server.log"
            print(f"server log written: {log.exists()}")
            if log.exists():
                tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
                print("  " + "\n  ".join(tail))
            # must not be reachable on other interfaces
            hostname_ip = socket.gethostbyname(socket.gethostname())
            if hostname_ip not in ("127.0.0.1", ""):
                status, _ = get(f"http://{hostname_ip}:{port}/_stcore/health", timeout=2)
                print(f"reachable on {hostname_ip}: {'YES - FAIL' if status == 200 else 'no (good)'}")
                ok &= status != 200
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        print(f"server stopped: {proc.poll() is not None}")
        ok &= proc.poll() is not None
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
