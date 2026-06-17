from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.settings import load_settings


def main() -> None:
    settings = load_settings()
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT_DIR / "streamlit_app.py"),
        "--server.port",
        str(settings.streamlit_server_port),
        "--server.headless",
        str(settings.streamlit_server_headless).lower(),
    ]
    subprocess.run(command, check=True, cwd=ROOT_DIR)


if __name__ == "__main__":
    main()
