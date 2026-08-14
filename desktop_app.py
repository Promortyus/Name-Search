from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


APP_DIR = Path(__file__).resolve().parent
APP_NAME = "姓名学取名工具"
DEFAULT_PORT = 8502
DEFAULT_HOST = "localhost"


def app_support_dir() -> Path:
    return Path(os.environ.get("NAME_SEARCH_DATA_DIR", Path.home() / "Library/Application Support" / APP_NAME)).expanduser()


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def wait_for_server(url: str, timeout_seconds: int = 45) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.5) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def ensure_character_db(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "characters.csv"
    source = APP_DIR / "characters.csv"
    if not target.exists() and source.exists():
        target.write_bytes(source.read_bytes())


def start_streamlit(host: str, port: int, data_dir: Path, log_file: Path) -> subprocess.Popen | None:
    if port_is_open(host, port):
        return None

    env = os.environ.copy()
    env["NAME_SEARCH_DATA_DIR"] = str(data_dir)
    env["PYTHONNOUSERSITE"] = "1"
    env.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    log_handle = log_file.open("a", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP_DIR / "app.py"),
            "--server.port",
            str(port),
            "--server.address",
            host,
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=APP_DIR,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_streamlit(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=3)


def run_smoke_check(url: str, process: subprocess.Popen | None) -> int:
    ok = wait_for_server(url)
    stop_streamlit(process)
    print("desktop smoke ok" if ok else "desktop smoke failed")
    return 0 if ok else 1


def main() -> int:
    host = os.environ.get("NAME_SEARCH_HOST", DEFAULT_HOST)
    port = int(os.environ.get("NAME_SEARCH_PORT", DEFAULT_PORT))
    url = f"http://{host}:{port}"
    data_dir = app_support_dir()
    log_file = data_dir / "desktop.log"

    ensure_character_db(data_dir)
    process = start_streamlit(host, port, data_dir, log_file)

    if os.environ.get("NAME_SEARCH_DESKTOP_SMOKE") == "1":
        return run_smoke_check(url, process)

    if not wait_for_server(url):
        stop_streamlit(process)
        raise RuntimeError(f"Streamlit 服务启动失败，请查看日志：{log_file}")

    import webview

    window = webview.create_window(
        APP_NAME,
        url,
        width=1440,
        height=940,
        min_size=(1060, 720),
        text_select=True,
    )
    try:
        webview.start()
    finally:
        stop_streamlit(process)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
