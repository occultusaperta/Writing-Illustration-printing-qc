from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional


def launch_ui(host: str = "127.0.0.1", port: int = 8501) -> int:
    cmd = [
        "streamlit",
        "run",
        "-m",
        "bookforge.ui.app",
        "--server.address",
        host,
        "--server.port",
        str(port),
    ]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        fallback = [
            "streamlit",
            "run",
            str((Path(__file__).with_name("app.py")).resolve()),
            "--server.address",
            host,
            "--server.port",
            str(port),
        ]
        proc = subprocess.run(fallback)
    return proc.returncode


def main(host: Optional[str] = None, port: Optional[int] = None) -> int:
    return launch_ui(host or "127.0.0.1", port or 8501)


if __name__ == "__main__":
    sys.exit(main())
