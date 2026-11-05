"""Desktop launcher helpers and the data-folder layout rules in config.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import desktop_main as dm

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------- launcher helpers
def test_find_free_port_is_bindable():
    port = dm.find_free_port()
    assert 1024 < port < 65536
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))      # still free immediately afterwards


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):                       # noqa: N802 - http.server API
        body = b"ok" if self.path == "/_stcore/health" else b"nope"
        self.send_response(200 if body == b"ok" else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):           # silence
        pass


@pytest.fixture
def health_server():
    server = HTTPServer(("127.0.0.1", 0), _Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


def test_wait_for_server_detects_healthy_endpoint(health_server):
    assert dm.server_is_healthy(health_server)
    assert dm.wait_for_server(health_server, process=None, timeout=5)


def test_wait_for_server_gives_up_when_process_dies():
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(3)"])
    port = dm.find_free_port()
    assert dm.wait_for_server(port, proc, timeout=10) is False
    assert proc.poll() == 3


def test_wait_for_server_times_out_on_silent_port():
    assert dm.wait_for_server(dm.find_free_port(), process=None, timeout=1.0, interval=0.2) is False


def test_urls_bind_to_loopback_only():
    assert dm.app_url(8765) == "http://127.0.0.1:8765/"
    assert dm.health_url(8765).startswith("http://127.0.0.1:8765/")


def test_parse_args_modes():
    args = dm.parse_args(["--serve", "--port", "5555", "--parent-pid", "42"])
    assert args.serve and args.port == 5555 and args.parent_pid == 42
    assert not dm.parse_args([]).serve
    assert dm.parse_args(["--self-test"]).self_test


def test_loading_and_error_pages_mention_the_app():
    assert dm.APP_TITLE in dm.loading_html()
    page = dm.error_html("Boom", "details here", Path("C:/x/launcher.log"))
    assert "Boom" in page and "details here" in page and "launcher.log" in page


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named mutex")
def test_single_instance_mutex_blocks_second_acquire():
    first = dm.SingleInstance("Local\\DMTM.test." + str(os.getpid()))
    second = dm.SingleInstance(first.name)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    second.release()


@pytest.mark.skipif(sys.platform != "win32", reason="registry lookup")
def test_webview2_detection_returns_bool():
    assert isinstance(dm.webview2_runtime_installed(), bool)


# ------------------------------------------------------------- config layouts
def _config_paths(env: dict[str, str], prelude: str = "") -> dict[str, str]:
    """Import config.py in a fresh interpreter and return its resolved folders."""
    script = textwrap.dedent(f"""
        import json, sys
        sys.path.insert(0, {str(ROOT)!r})
        {prelude}
        import config
        print(json.dumps({{k: str(getattr(config, k)) for k in
              ("DATA_DIR", "EXPORT_DIR", "BACKUP_DIR", "LOG_DIR", "DB_PATH", "IS_FROZEN", "IS_PORTABLE")}}))
    """)
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("DMTM_")}
    full_env.update(env)
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=full_env, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_development_layout_uses_project_folders():
    paths = _config_paths({})
    assert paths["DATA_DIR"] == str(ROOT / "data")
    assert paths["EXPORT_DIR"] == str(ROOT / "exports")
    assert paths["BACKUP_DIR"] == str(ROOT / "data" / "backups")
    assert paths["IS_FROZEN"] == "False"


def test_data_dir_override_moves_everything(tmp_path):
    paths = _config_paths({"DMTM_DATA_DIR": str(tmp_path)})
    assert paths["DATA_DIR"] == str(tmp_path)
    assert paths["EXPORT_DIR"] == str(tmp_path / "exports")
    assert paths["BACKUP_DIR"] == str(tmp_path / "backups")
    assert paths["DB_PATH"] == str(tmp_path / "database.db")


def test_frozen_layout_uses_local_appdata(tmp_path):
    local = tmp_path / "LocalAppData"
    prelude = f"sys.frozen = True; sys._MEIPASS = {str(tmp_path / 'bundle')!r}; sys.executable = {str(tmp_path / 'App' / 'x.exe')!r}"
    paths = _config_paths({"LOCALAPPDATA": str(local)}, prelude)
    assert paths["IS_FROZEN"] == "True" and paths["IS_PORTABLE"] == "False"
    assert paths["DATA_DIR"] == str(local / "DailyMoneyTransferManager")
    assert paths["DB_PATH"] == str(local / "DailyMoneyTransferManager" / "database.db")
    assert paths["LOG_DIR"] == str(local / "DailyMoneyTransferManager" / "logs")
    # never inside the bundle / temp extraction folder
    assert not paths["DB_PATH"].startswith(str(tmp_path / "bundle"))


def test_portable_marker_keeps_data_next_to_executable(tmp_path):
    exe_dir = tmp_path / "Portable"
    exe_dir.mkdir()
    (exe_dir / "portable.txt").write_text("portable")
    prelude = f"sys.frozen = True; sys._MEIPASS = {str(exe_dir / '_internal')!r}; sys.executable = {str(exe_dir / 'x.exe')!r}"
    paths = _config_paths({"LOCALAPPDATA": str(tmp_path / "ignored")}, prelude)
    assert paths["IS_PORTABLE"] == "True"
    assert paths["DATA_DIR"] == str(exe_dir / "data")


# ------------------------------------------------------------- failure paths
def test_missing_webview2_is_reported_and_exits_cleanly(monkeypatch, tmp_path, capsys):
    """Simulated: the WebView2 check fails -> user message, exit code 4, no server started."""
    shown = []
    monkeypatch.setattr(dm, "webview2_runtime_installed", lambda: False)
    monkeypatch.setattr(dm, "_message_box", lambda text, title=dm.APP_TITLE, icon=0: shown.append(text))
    monkeypatch.setattr(dm, "start_server_process", lambda port: pytest.fail("server must not start"))
    monkeypatch.setattr(dm, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(dm, "EXCEL_EXPORT_DIR", tmp_path / "exports" / "excel")
    monkeypatch.setattr(dm, "REPORT_EXPORT_DIR", tmp_path / "exports" / "reports")
    monkeypatch.setattr(sys, "platform", "win32")
    assert dm.run_desktop() == 4
    assert shown and "WebView2" in shown[0] and "developer.microsoft.com" in shown[0]
    # in development mode the launcher logs to the console (the packaged app redirects to launcher.log)
    assert "WebView2 runtime not found" in capsys.readouterr().out


def test_second_instance_exits_with_notice(monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(dm.SingleInstance, "acquire", lambda self: False)
    monkeypatch.setattr(dm, "_message_box", lambda text, title=dm.APP_TITLE, icon=0: shown.append(text))
    monkeypatch.setattr(dm, "start_server_process", lambda port: pytest.fail("server must not start"))
    for name in ("LOG_DIR", "DATA_DIR", "BACKUP_DIR", "EXCEL_EXPORT_DIR", "REPORT_EXPORT_DIR"):
        monkeypatch.setattr(dm, name, tmp_path / name.lower())
    assert dm.run_desktop() == 3
    assert shown and "already running" in shown[0]
