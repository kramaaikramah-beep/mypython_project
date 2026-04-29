from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
API_HOST = "127.0.0.1"
API_PORT = 8000
UI_PORT = 8501


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _wait_for_port(host: str, port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    load_dotenv(ROOT_DIR / ".env")
    env = os.environ.copy()
    env["ASSESSMENT_API_URL"] = f"http://{API_HOST}:{API_PORT}"

    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.api.main:app",
        "--host",
        API_HOST,
        "--port",
        str(API_PORT),
    ]
    ui_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT_DIR / "frontend" / "app.py"),
        "--server.headless",
        "true",
        "--server.port",
        str(UI_PORT),
        "--browser.gatherUsageStats",
        "false",
    ]

    api_process = subprocess.Popen(api_cmd, cwd=ROOT_DIR, env=env)
    try:
        if not _wait_for_port(API_HOST, API_PORT):
            print("Backend did not start on time.", file=sys.stderr)
            _terminate(api_process)
            return 1

        ui_process = subprocess.Popen(ui_cmd, cwd=ROOT_DIR, env=env)
        print(f"Backend: http://{API_HOST}:{API_PORT}")
        print(f"Frontend: http://127.0.0.1:{UI_PORT}")
        print("Press Ctrl+C to stop both services.")

        try:
            while True:
                if api_process.poll() is not None:
                    print("Backend process stopped.", file=sys.stderr)
                    break
                if ui_process.poll() is not None:
                    print("Frontend process stopped.", file=sys.stderr)
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            _terminate(ui_process)
    finally:
        _terminate(api_process)

    return 0


if __name__ == "__main__":
    if os.name == "nt":
        signal.signal(signal.SIGINT, signal.default_int_handler)
    raise SystemExit(main())
