# -*- coding: utf-8 -*-
"""
대치스카이부동산을 데스크톱 창(프로그램)처럼 띄우는 실행 파일 진입점.
동작 방식: 이 exe 자신을 "서버용 자식 프로세스"로 한 번 더 실행해서 거기서 Streamlit 서버를
띄우고, 부모 프로세스는 그 주소를 pywebview 창으로 열어서 보여준다. 창을 닫으면 자식(서버)도 같이 끈다.
"""

import os
import subprocess
import sys
import time
import urllib.request

APP_TITLE = "대치스카이부동산"
CHILD_FLAG = "--server-child"


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def find_free_port() -> int:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_as_streamlit_server(port: int) -> None:
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        resource_path("main_app.py"),
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]
    sys.exit(stcli.main())


def wait_for_server(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}"
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def spawn_server(port: int) -> subprocess.Popen:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, CHILD_FLAG, str(port)]
    else:
        cmd = [sys.executable, os.path.abspath(__file__), CHILD_FLAG, str(port)]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(cmd, creationflags=creationflags)


def main() -> None:
    if CHILD_FLAG in sys.argv:
        port = int(sys.argv[sys.argv.index(CHILD_FLAG) + 1])
        run_as_streamlit_server(port)
        return

    port = find_free_port()
    proc = spawn_server(port)
    try:
        if not wait_for_server(port):
            raise RuntimeError("서버가 제한 시간 안에 시작되지 않았습니다.")

        import webview

        webview.create_window(APP_TITLE, f"http://127.0.0.1:{port}", width=1360, height=900)
        webview.start()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
