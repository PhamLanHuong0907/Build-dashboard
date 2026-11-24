"""Standalone Desktop App Launcher for Auto-PBI Dashboard Studio (.exe).

Double-click AutoPBI_Studio.exe:
  1. Uses the folder containing AutoPBI_Studio.exe as the local workspace.
  2. Starts the local Flask server on an available port (default 8505).
  3. Opens a native-looking Desktop App window via Microsoft Edge / Chrome --app mode
     (falls back to default browser if neither is found).

Also supports CLI arguments (--csv, --req, --project-name, --open-pbi, --port, --no-browser).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _ensure_workspace_dirs(root: Path) -> None:
    for sub in ("inputs", "custom_visuals", "data_warehouse", "output_pbi", "reports", "config"):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _find_chromium_browser() -> str | None:
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _open_desktop_window(url: str) -> None:
    browser = _find_chromium_browser()
    if browser:
        try:
            subprocess.Popen(
                [browser, f"--app={url}", "--window-size=1440,900"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    webbrowser.open(url)


def main() -> None:
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    root = get_app_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _ensure_workspace_dirs(root)

    # If user invokes CLI pipeline flags, delegate to src.main
    cli_flags = {"--csv", "--req", "--project-name", "--skip-etl", "--open-pbi", "--help", "-h"}
    if any(arg in cli_flags for arg in sys.argv[1:]):
        from src.main import main as cli_main
        if "--workspace" not in sys.argv[1:]:
            sys.argv.extend(["--workspace", str(root)])
        cli_main()
        return

    # Parse optional --port / --no-browser
    port = 8505
    open_window = True
    args = sys.argv[1:]
    for idx, a in enumerate(args):
        if a == "--port" and idx + 1 < len(args):
            try:
                port = int(args[idx + 1])
            except ValueError:
                pass
        elif a == "--no-browser":
            open_window = False

    from src.web_ui import _find_free_port, create_app

    port = _find_free_port(port)
    url = f"http://127.0.0.1:{port}"
    app = create_app(str(root))

    # Quiet Werkzeug request logs for a cleaner app console
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    print("=" * 74)
    print("  AUTO-PBI DASHBOARD STUDIO (Windows Desktop App)")
    print(f"  Dia chi ung dung : {url}")
    print(f"  Thu muc du lieu  : {root}")
    print("  Moi du lieu luu cuc bo tren may ban. Dong cua so nay de thoat app.")
    print("=" * 74)

    if open_window:
        threading.Timer(1.0, _open_desktop_window, args=(url,)).start()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
