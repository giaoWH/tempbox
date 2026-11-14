# TempBox

**Temporary files deserve a temporary home.**

TempBox is a small, native macOS menu bar app that gives temporary files a dedicated
home. Drag files from Finder into TempBox; they are moved into TempBox's own folder,
kept for a chosen period, and then automatically moved to the macOS Trash.

> **Status: Phase 2 (v0.2).** Retention times, live countdowns and automatic Trash
> clean-up work. Search, batch actions, global settings, Finder integration and
> packaging are planned for later phases.

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

The main window opens and a box icon appears in the macOS menu bar.

## Usage

- **Click the menu bar icon** to show or hide the main window. TempBox has no Dock
  icon; it lives only in the menu bar.
- **Drag files from Finder** into the window (single or multiple files). Folders,
  symbolic links and other special files are rejected.
- **New files are kept for 1 day by default.** Select a file and open the
  **Retention** menu to choose 1 hour, 1 day, 7 days, 30 days, or a custom date and
  time. Custom times must be in the future.
- The **Remaining** column updates every 30 seconds. It turns amber when less than
  one hour is left and red when the file is expired or its clean-up failed. Hover a
  failed row to see the error.
- **When a file expires it is moved to the macOS Trash**, so it can still be
  recovered from the Trash. An overdue check also runs when the app starts.
  Failed clean-ups are retried on the next 30-second check.
- Files imported by Phase 1 show **No expiry** and are never cleaned up
  automatically; use the Retention menu to give them a deadline.
- Select a file and use **Open**, **Show in Finder** or **Restore**. Restore puts
  the file back at its original path (or asks for another folder if needed) and
  never overwrites existing files.
- Closing the window hides it; TempBox keeps running in the menu bar.
- **Quit** with the window's **Quit** button (bottom right) or `Cmd+Q` while the
  window is focused. On macOS 27, Qt reports status item clicks without mouse button
  information, so a right-click behaves like a normal click and the tray menu may
  not open on that macOS version.

## Data location

```
~/Library/Application Support/TempBox/
├── files/<uuid>/<original-name>   # files managed by TempBox
├── records.json                   # metadata index (atomic writes, version 2)
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
real macOS Trash behaviour was verified manually with throwaway files. Menu bar
clicks and real Finder drags are verified manually (see the Phase 2 acceptance
notes).

## Known limitations (Phase 2)

- The default retention is fixed at 1 day; it is not configurable yet (Phase 3).
- No search, sorting, batch operations or settings page yet (Phase 3).
- Clean-up and file moves run on the GUI thread; fine for typical temporary files.
- Failed clean-ups are retried every 30 seconds while the app is running; there is
  no separate retry schedule or backoff.
- The countdown has 30-second resolution.
- English-only UI.
- TempBox runs without a Dock icon (accessory activation policy).
- On macOS 27 the Qt tray reports clicks as `Unknown`, so the right-click tray menu
  may not be available; quit from the window or with `Cmd+Q`.
- On this machine `Send2Trash` uses its ctypes backend (PyObjC is not installed);
  it was verified to move files to the macOS Trash with their original names.
