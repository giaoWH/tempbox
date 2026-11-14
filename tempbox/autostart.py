"""Launch-at-login support using a per-user LaunchAgent.

TempBox is not bundled as a .app yet, so the agent starts the current Python
interpreter and main.py directly. Moving the project or the Conda environment
means toggling this setting off and on again.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.tempbox.app"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def is_enabled() -> bool:
    return _plist_path().exists()


def set_enabled(enabled: bool) -> None:
    if enabled:
        _write_plist()
    else:
        _remove_plist()


def _write_plist() -> None:
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path.home() / "Library" / "Logs" / "TempBox.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            str(Path(sys.executable).resolve()),
            str(_PROJECT_ROOT / "main.py"),
            "--hidden",
        ],
        "WorkingDirectory": str(_PROJECT_ROOT),
        "RunAtLoad": True,
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    temporary_path = path.with_suffix(".tmp")
    with open(temporary_path, "wb") as handle:
        plistlib.dump(payload, handle)
    os.replace(temporary_path, path)


def _remove_plist() -> None:
    path = _plist_path()
    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
            check=False,
            capture_output=True,
        )
    except OSError:
        pass
    try:
        path.unlink()
    except FileNotFoundError:
        pass
