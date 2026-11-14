# TempBox

**Temporary files deserve a temporary home.**

TempBox is a small, native macOS menu bar app that gives temporary files a dedicated
home. Drag files from Finder into TempBox; they are moved into TempBox's own folder,
kept for a chosen period, and then automatically moved to the macOS Trash.

> **Status: Phase 3 (v0.3).** File management, retention, automatic Trash clean-up,
> search, sorting, multi-select batch actions, a configurable default retention,
> launch at login and light/dark appearance are implemented. Finder integration,
> packaging and signing are planned for Phase 4.

## Requirements

- macOS on Apple Silicon (developed and tested on macOS 27.0.1)
- Conda (Miniconda or Anaconda)

## Setup

Verified on this machine: Python 3.14.10, PySide6 6.12.0, Send2Trash 2.2.0
(Apple Silicon, macOS 27.0.1).

```bash
conda create -n tempbox -c conda-forge --override-channels python=3.14 pip
conda activate tempbox
pip install PySide6==6.12.0 Send2Trash==2.2.0
```

`environment.yml` records the same environment declaratively. On some newer Conda
installations (e.g. Conda 26.x with the Anaconda `defaults` channel configured),
`conda env create -f environment.yml` can stop with a
`CondaToSNonInteractiveError` about the Anaconda repository Terms of Service.
Either accept the Terms of Service (Conda prints the command) or use the explicit
commands above, which bypass the `defaults` channel.

## Run

```bash
python main.py
```

The main window opens under the menu bar icon and a box icon appears in the menu bar.

## Usage

- **Click the menu bar icon** to show or hide the window. It appears just below the
  icon, centered on it, and takes focus. Clicking outside TempBox hides it again.
  Closing the window also hides it; TempBox keeps running in the menu bar.
- **Drag files from Finder** into the window. New files use the current default
  retention (1 day unless changed). Folders and symbolic links are rejected.
- **Search** by file name with the search field (case-insensitive, live filtering).
  **Sort** by added time, name, size or expiry time in the sort menu.
- **Select one or more files** (Command/Shift click). The bottom buttons and the
  right-click menu work on the selection:
  - **Open**, **Show in Finder** (single selection only)
  - **Restore** — restores all selected files to their original paths; conflicts
    and missing folders are reported without affecting the other files. A single
    selected file can still be restored to a folder of your choice.
  - **Expiration** / **Change Expiration** — 1 hour, 1 day, 7 days, 30 days, or a
    custom date and time. Applied to all selected files.
- New files expire by default after the configured default retention; expired files
  are moved to the macOS Trash and can be recovered from there. An overdue check
  also runs at startup; failed clean-ups are retried every 30 seconds.
- Files imported by Phase 1 show **No expiry** and are never cleaned automatically.
- The header shows the total number of files and their combined size.
- **Settings…** (bottom right) configures the default retention for new files and
  whether TempBox launches at login. Closing the window hides it; use **Quit** or
  `Cmd+Q` to exit.
- On macOS 27, Qt reports status item clicks without mouse button information, so a
  right-click behaves like a normal click and the tray menu may not open. All file
  actions are also available in the window and its context menu.

### Launch at login

Enabling it writes a user LaunchAgent:
`~/Library/LaunchAgents/com.tempbox.app.plist`. It starts TempBox with `--hidden`
(menu bar only) on the next login and appends output to `~/Library/Logs/TempBox.log`.
While TempBox runs as a Python script, the agent embeds the current Python
interpreter and project paths; if either moves, turn the setting off and on again.
Because the agent is written but not loaded immediately, enabling it never starts a
second copy of the running app.

## Data location

```
~/Library/Application Support/TempBox/
├── files/<uuid>/<original-name>   # files managed by TempBox
├── records.json                   # metadata index (atomic writes, version 2)
├── settings.json                  # default retention preference (atomic writes)
└── .instance.lock                 # single-instance lock
```

`records.json` stores `expires_at` (UTC ISO 8601) and an optional `trash_error` for
failed clean-ups. Phase 1 indexes (version 1) load unchanged: their records simply
have no expiry and are never auto-cleaned; the index is upgraded to version 2 the
next time it is saved.

Safety rules for automatic clean-up:

- only files recorded by TempBox, located inside TempBox storage, still being
  regular files, and past their own expiry time are touched;
- files are moved with `Send2Trash` (never permanently deleted);
- missing files are reported and their records kept, never treated as cleaned;
- failed clean-ups keep both the file and its record, with the error persisted;
- a crash between the Trash move and the index write is detected on the next load
  as a missing stored file and is not retried destructively.

## Tests

```bash
conda activate tempbox
python -m unittest discover -s tests -t . -v
```

Storage tests mock `send2trash`; window tests use Qt's `offscreen` platform. The
real macOS Trash behaviour and the light/dark appearance were verified manually with
throwaway files. Menu bar clicks, click-outside hiding and the login launch itself
are verified manually (see the Phase 3 acceptance notes).

## Known limitations (Phase 3)

- The default retention applies to newly imported files only; existing files keep
  their own expiry times.
- No batch permanent deletion exists (by design), and missing-file records have no
  UI removal action yet.
- Failed clean-ups are retried every 30 seconds while the app runs; there is no
  separate retry schedule or backoff.
- The countdown has 30-second resolution.
- Clean-up and file moves run on the GUI thread; fine for typical temporary files.
- Search matches file names only (no content search) and sorting is UI-only.
- The window position under the menu bar icon depends on macOS reporting the status
  item geometry; the first show is deferred by ~0.2 seconds to get a correct
  position.
- Clicking outside hides the window, but app-owned dialogs and menus keep it open.
- Launch at login is implemented for the script-based development setup and has not
  been verified across an actual logout/login in automated tests. It is expected to
  be replaced by the bundled `.app` login item in Phase 4.
- On macOS 27 the Qt tray reports clicks as `Unknown`, so the right-click tray menu
  may not be available; use the window or `Cmd+Q` to quit.
- On this machine `Send2Trash` uses its ctypes backend (PyObjC is not installed); it
  was verified to move files to the macOS Trash with their original names.
