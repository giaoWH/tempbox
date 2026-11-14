"""Finder Quick Action ("Move to TempBox") and its background import helper.

The Quick Action is an Automator service workflow in ``~/Library/Services``. Its
Run Shell Script action calls this module in a separate process, reusing the
same FileStore import logic (and the same cross-process index lock) as the app.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from . import __version__
from .paths import data_dir
from .settings import AppSettings
from .storage import FileStore, ImportResult

WORKFLOW_NAME = "Move to TempBox"
WORKFLOW_FILENAME = WORKFLOW_NAME + ".workflow"
SERVICES_DIRNAME = "Services"

_INFO_PLIST = {
    "CFBundleDevelopmentRegion": "en",
    "CFBundleIdentifier": "com.tempbox.quickaction",
    "CFBundleName": WORKFLOW_NAME,
    "CFBundlePackageType": "BNDL",
    "CFBundleShortVersionString": __version__,
    "CFBundleVersion": __version__,
    "NSServices": [
        {
            "NSMenuItem": {"default": WORKFLOW_NAME},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": ["public.item"],
        }
    ],
}


def services_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / SERVICES_DIRNAME


def workflow_path(home: Path | None = None) -> Path:
    return services_dir(home) / WORKFLOW_FILENAME


def is_installed(home: Path | None = None) -> bool:
    path = workflow_path(home)
    return (path / "Contents" / "Info.plist").is_file() and (
        path / "Contents" / "Resources" / "document.wflow"
    ).is_file()


def _refresh_services() -> bool:
    """Ask macOS to re-read the user Services folder.

    Copying a workflow into ~/Library/Services is not always enough on its own;
    pbs -update makes Finder/System Settings notice it without a logout.
    """
    pbs = Path("/System/Library/CoreServices/pbs")
    if not pbs.exists():
        return False
    try:
        subprocess.run(
            [str(pbs), "-update"],
            check=False,
            capture_output=True,
            timeout=5,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _workflow_document(command: str) -> dict:
    def new_uuid() -> str:
        return str(uuid.uuid4()).upper()

    action = {
        "AMAccepts": {
            "Container": "List",
            "Optional": True,
            "Types": ["com.apple.cocoa.string"],
        },
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {
            "COMMAND_STRING": {},
            "CheckedForUserDefaultShell": {},
            "inputMethod": {},
            "shell": {},
            "source": {},
        },
        "AMProvides": {
            "Container": "List",
            "Types": ["com.apple.cocoa.string"],
        },
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {
            "COMMAND_STRING": command,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 1,
            "shell": "/bin/bash",
            "source": "",
        },
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": new_uuid(),
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": new_uuid(),
        "UUID": new_uuid(),
        "UnlocalizedApplications": ["Automator"],
        "arguments": {
            "0": {
                "default value": 1,
                "name": "inputMethod",
                "required": "0",
                "type": "0",
                "uuid": "0",
            },
            "1": {
                "default value": "",
                "name": "source",
                "required": "0",
                "type": "0",
                "uuid": "1",
            },
            "2": {
                "default value": True,
                "name": "CheckedForUserDefaultShell",
                "required": "0",
                "type": "0",
                "uuid": "2",
            },
            "3": {
                "default value": "",
                "name": "COMMAND_STRING",
                "required": "0",
                "type": "0",
                "uuid": "3",
            },
            "4": {
                "default value": "/bin/bash",
                "name": "shell",
                "required": "0",
                "type": "0",
                "uuid": "4",
            },
        },
        "isViewVisible": True,
        "location": "309.500000:631.000000",
        "nibPath": (
            "/System/Library/Automator/Run Shell Script.action/Contents/Resources/"
            "en.lproj/main.nib"
        ),
    }
    return {
        "AMApplicationBuild": "346",
        "AMApplicationVersion": "2.3",
        "AMDocumentVersion": "2",
        "actions": [{"action": action, "isViewVisible": True}],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleID": "com.apple.finder",
            "applicationBundleIDsByPath": {
                "/System/Library/CoreServices/Finder.app": "com.apple.finder"
            },
            "applicationPaths": ["/System/Library/CoreServices/Finder.app"],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": 1,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def shell_command(project_root: Path | str | None = None, python: str | None = None) -> str:
    project = Path(project_root or Path(__file__).resolve().parent.parent)
    executable = python or sys.executable
    return (
        f"cd {shlex.quote(str(project))} && "
        f"{shlex.quote(executable)} -m tempbox.quick_action \"$@\""
    )


def install(
    home: Path | None = None,
    project_root: Path | str | None = None,
    python: str | None = None,
) -> Path:
    """Install/update the Finder Quick Action. Returns the workflow path."""
    path = workflow_path(home)
    contents = path / "Contents"
    resources = contents / "Resources"
    if path.exists():
        if path.is_symlink() or path.is_file():
            raise OSError(f"{path} is not a directory")
        shutil.rmtree(path)
    resources.mkdir(parents=True)
    with open(contents / "Info.plist", "wb") as handle:
        plistlib.dump(_INFO_PLIST, handle, sort_keys=False)
    with open(resources / "document.wflow", "wb") as handle:
        plistlib.dump(
            _workflow_document(shell_command(project_root, python)),
            handle,
            sort_keys=False,
        )
    _refresh_services()
    return path


def uninstall(home: Path | None = None) -> bool:
    path = workflow_path(home)
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_dir():
        raise OSError(f"{path} is not a workflow directory")
    shutil.rmtree(path)
    _refresh_services()
    return True


def _default_data_dir() -> Path:
    override = os.environ.get("TEMPBOX_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return data_dir()


def import_paths(
    paths: list[Path | str],
    root: Path | str | None = None,
) -> ImportResult:
    """Import Finder selections through the normal, locked FileStore path."""
    data_root = Path(root) if root is not None else _default_data_dir()
    settings = AppSettings.load(data_root)
    store = FileStore(data_root)
    store.load()
    store.default_retention = settings.default_retention
    return store.import_files([Path(path) for path in paths])


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    paths = [Path(argument) for argument in arguments if argument]
    if not paths:
        return 0
    try:
        result = import_paths(paths)
    except (OSError, ValueError) as exc:
        print(f"TempBox: {exc}", file=sys.stderr)
        return 1
    if result.failed:
        for name, reason in result.failed:
            print(f"TempBox: could not move '{name}': {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
