# TempBox Development Guide

English | [简体中文](DEVELOPMENT.zh-CN.md)

This document is for developers running TempBox from source. For user-facing behavior
see [USAGE.md](USAGE.md).

## Requirements

- macOS (Apple Silicon tested on macOS 27.0.1)
- Conda / Miniconda
- Python 3.14 (verified 3.14.10)
- PySide6 6.12.0
- Send2Trash 2.2.0
- PyInstaller 6.22.3 (build only)

No test framework is required; the suite uses the standard library `unittest`.

## Environment setup

Preferred:

```bash
conda env create -f environment.yml
conda activate tempbox
```

If Conda stops with a `CondaToSNonInteractiveError` because the Anaconda `defaults`
channel Terms of Service have not been accepted, bypass `defaults`:

```bash
conda create -n tempbox -c conda-forge --override-channels python=3.14 pip
conda activate tempbox
pip install PySide6==6.12.0 Send2Trash==2.2.0
```

Never commit a local environment. The repository ignores common environment folders.

## Run

```bash
cd /path/to/tempbox
conda activate tempbox
python main.py
```

`python main.py --hidden` starts from the menu bar without showing the panel (used by
the login LaunchAgent). Development runs use the current Python/project paths for
login launch and Finder integration; the packaged app uses the app binary instead.

## Build the macOS app and DMG

The release build targets Apple Silicon (arm64), is a PyInstaller one-directory app,
and is intentionally not Developer ID signed or notarized for v1.0.0.

```bash
conda activate tempbox
python -m pip install -r requirements-build.txt
PYTHON="$CONDA_PREFIX/bin/python" ./scripts/build_macos.sh
```

The script uses [TempBox.spec](../TempBox.spec), generates:

- `dist/TempBox.app`
- `dist/TempBox-1.0.0-macOS-arm64.dmg`
- `dist/TempBox-1.0.0-macOS-arm64.dmg.sha256`

`TempBox.spec` sets the bundle identifier (`com.tempbox.app`), version (read from
`tempbox/__init__.py`), `LSUIElement`, icon and the license/notice resources. The
build is ad-hoc signed by the PyInstaller bundling tools only; do not describe it as
Developer ID signed or notarized.

Independent packaged-app checks used during Phase 5:

```bash
# Menu-bar-only launch without Conda in the environment
env -i HOME=/tmp/tempbox-test TMPDIR=/tmp PATH=/usr/bin:/bin \
  dist/TempBox.app/Contents/MacOS/TempBox --hidden

# Headless Quick Action import path inside the bundle
env -i HOME=/tmp/tempbox-test TMPDIR=/tmp PATH=/usr/bin:/bin \
  dist/TempBox.app/Contents/MacOS/TempBox --quick-action /tmp/a-file
```

Mount the DMG with `hdiutil attach -nobrowse -readonly ...` and verify it contains
`TempBox.app`, an `Applications` symlink and the license files. Rebuild and recheck
after changing dependencies or the Qt/PyInstaller versions.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

Window tests use Qt's `offscreen` platform plugin. Storage tests use temporary
directories and mock `send2trash`; they never touch the user's real TempBox storage.
Tests that exercise the Quick Action generate workflows under a temporary home
directory and do not install anything into the real `~/Library/Services`.

Some macOS behaviors cannot be asserted reliably in automation:

- Finder Quick Action menu registration;
- visible delivery of Notification Center messages;
- menu bar clicks/focus and the visual appearance;
- real Trash behavior.

Manual acceptance is still required for these; the user guide covers the relevant
installation and troubleshooting steps.

## Project layout

```
.
├── main.py                  # entry point: python main.py
├── environment.yml          # Conda runtime environment
├── README.md                # project overview
├── README.zh-CN.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── LICENSE                  # Apache-2.0 for TempBox source
├── NOTICE
├── THIRD_PARTY_LICENSES.md  # third-party attribution and LGPL notes
├── TempBox.spec             # PyInstaller build definition
├── requirements-build.txt   # build-only PyInstaller pin
├── assets/TempBox.icns      # application icon
├── licenses/                # bundled third-party license texts
├── scripts/build_macos.sh   # .app + .dmg build entry point
├── docs/
│   ├── USAGE.md
│   ├── USAGE.zh-CN.md
│   ├── DEVELOPMENT.md
│   ├── DEVELOPMENT.zh-CN.md
│   ├── RELEASE_NOTES_v1.0.0.md
│   └── screenshots/         # screenshots of the real app
├── tempbox/
│   ├── app.py               # QApplication, tray icon, menu bar behavior, quit flow
│   ├── window.py            # floating panel (MainWindow) and panel logic
│   ├── ui_theme.py          # theme tokens, QSS, painted icons
│   ├── ui_widgets.py        # card/row/drop-zone/empty-state widgets
│   ├── dialogs.py           # expiry picker, Settings and History windows
│   ├── storage.py           # FileStore: import/restore/index/cleanup/locking
│   ├── history.py           # recently-cleaned history (metadata only)
│   ├── settings.py          # persisted preferences
│   ├── formatting.py        # size/date/plural display helpers
│   ├── paths.py             # shared data directory location
│   ├── autostart.py         # per-user LaunchAgent
│   ├── macos.py             # small AppKit/ctypes bridge (Dock/focus)
│   ├── quick_action.py      # Finder Quick Action installer + import helper
│   └── updates.py           # GitHub Releases update checker
└── tests/                   # unittest suite
```

Responsibilities follow the app's real boundaries rather than a framework:

- **UI**: `window.py`, `ui_theme.py`, `ui_widgets.py`, `dialogs.py` display data and
  collect user intent; they do not perform file moves themselves.
- **Core/storage**: `storage.py` owns all file movement and index mutation; `history.py`
  and `settings.py` own their respective persisted data.
- **Services**: `app.py` (menu bar/tray lifecycle), `quick_action.py` (Finder),
  `autostart.py` (login), `macos.py` (small native bridge), `updates.py` (GitHub
  Releases update checks).

Avoid adding a new module for a one-line helper; add one only when it has a clear,
independent responsibility. Do not introduce a framework or dependency injection layer
for this app size.

## Data storage

Root: `~/Library/Application Support/TempBox/` (see [paths.py](../tempbox/paths.py)).

```
files/<uuid>/<original-name>   managed files; original name preserved
records.json                   index (schema version 2)
history.json                   recent successful cleanup metadata (max 100)
settings.json                  preferences
.instance.lock                 single-instance lock (QLockFile)
.data.lock                     advisory fcntl lock for cross-process index access
```

`records.json` is JSON with `version: 2` and a `files` list. Each record contains:

- `id`, `original_name`, `original_path`;
- `stored_relative_path` (safe relative path under the data root);
- `size`, `added_at` (ISO 8601 with timezone);
- `expires_at` (UTC ISO 8601 or null) and optional `trash_error`.

Phase 1 version-1 indexes load unchanged; missing `expires_at` means "No expiration"
and the record is never cleaned automatically. The index is upgraded to version 2 the
next time it is saved. Do not rename or remove fields without adding compatibility and
tests for existing indexes.

`settings.json` holds `default_retention_seconds`, `pause_auto_cleanup` and
`remind_before_expiry`. Missing fields fall back to defaults (1 day, not paused,
reminders on).

`history.json` stores only metadata for successful Trash moves; it never stores file
contents. At most 100 entries are kept, newest first.

### Cross-process access

The app and the Finder Quick Action helper can both import files. `FileStore` uses an
advisory `fcntl.flock` on `.data.lock` around read-modify-write operations and reloads
the index if its timestamp changed. This prevents one process from overwriting another
process's records. `MainWindow` polls the index every two seconds (cheap stat check;
lock is only taken when it changed) so external imports appear promptly.

## File safety rules

These are intentional and must not be weakened:

- only records inside TempBox storage are cleaned;
- only regular files are imported/cleaned (no symlinks, folders or special files);
- import supports cross-device moves and never overwrites stored files (unique UUID
  folders);
- restore never overwrites an existing destination; conflicts ask for a new folder;
- files are moved to Trash with `Send2Trash`, never permanently deleted by cleanup;
- failed Trash moves keep both file and index record for retry;
- missing stored files are reported and records retained;
- index writes are atomic (`tmp` + `os.replace`);
- corrupted indexes are backed up before being rebuilt/emptied;
- paused cleanup must survive restart and must not be bypassed by timers.

Changes to these paths need regression tests in `tests/test_storage.py` and
`tests/test_window.py`.

## Finder Quick Action

`quick_action.py` installs an Automator `.workflow` into `~/Library/Services` and calls
`/System/Library/CoreServices/pbs -update` so macOS re-reads the service list. The
workflow's Run Shell Script action executes, in a source checkout:

```bash
cd "<project>" && "<python>" -m tempbox.quick_action "$@"
```

In the packaged app it executes the app binary directly:

```bash
"/Applications/TempBox.app/Contents/MacOS/TempBox" --quick-action "$@"
```

`main.py` handles `--quick-action` before creating `QApplication`, so this is a
headless import process. The helper loads `settings.json`, creates a normal
`FileStore`, applies the default retention and imports the selected files. This
deliberately reuses the same safety and locking path as the app. If TempBox is already
running, its 2-second index poll shows the changes without an IPC protocol.

The workflow is generated from plist dictionaries in `quick_action.py`; it was
validated end-to-end with `/usr/bin/automator` in a temporary home directory and the
packaged `--quick-action` entry point was tested independently. Finder service
registration/caching still needs manual verification; see USAGE.md for
troubleshooting. Moving the `.app` requires reinstalling the Quick Action.

## Update checks

`updates.py` uses the confirmed repository (`https://github.com/giaoWH/tempbox`) and
the GitHub `/releases/latest` API. The Settings UI runs the network request on a
background thread and emits a queued Qt signal; it never blocks the GUI. Statuses
distinguish `up_to_date`, `update_available`, `no_release`, `network_error` and
`api_error`. No background checks, downloads, replacement or restart are implemented.

## Login launch and packaged paths

`autostart.py` writes `com.tempbox.app.plist` with the current interpreter plus
`main.py` during development, and with the app binary plus `--hidden` when frozen.
The LaunchAgent uses the same bundle label as the app bundle identifier. Moving the
app or the source checkout requires toggling the setting off and on again.

## Notifications, pause and reminders

- `MainWindow` owns UI-level scheduling for cleanup (30 s), reminders (same tick) and
  external index sync (2 s).
- Notifications go through a callback set by `app.py` to
  `QSystemTrayIcon.showMessage`; failures are isolated and never block cleanup.
- Reminder state is in-memory for the running app; history and pause are persisted.
- Pause/resume confirmation remains in the main window; a cancelled resume writes the
  paused setting back so future timer ticks cannot clean silently.

## Code style

- Python 3.14, `from __future__ import annotations`, standard typing.
- Keep functions focused; use comments only for non-obvious behavior or safety rules.
- Prefer standard library utilities; avoid new dependencies for small tasks.
- Keep UI text concise and consistent with the existing panel.
- Preserve the float panel layout; do not reintroduce a table-style main window.
- Run compileall/tests after changes.
- Do not commit personal data, logs, environment folders or build artifacts.

## Licensing

TempBox source is Apache-2.0; see [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
Third-party components are covered by their own licenses; PySide6/Qt use the LGPL-3.0
option, and bundled license texts plus source references are in
[THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md) and `licenses/`. Keep these files
in the app and DMG when changing the build.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md).
