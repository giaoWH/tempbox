# TempBox

**Temporary files deserve a temporary home.**

TempBox is a small, native macOS menu bar app that gives temporary files a dedicated
home. Drag files from Finder into TempBox; they are moved into TempBox's own folder
and can be opened, revealed in Finder, or restored to their original location later.

> **Status: Phase 1 (v0.1).** Storing and restoring files works. Automatic expiry,
> search, batch operations and packaging are planned for later phases.

## Requirements

- macOS on Apple Silicon (developed and tested on macOS 27.0.1)
- Conda (Miniconda or Anaconda)

## Setup

Verified on this machine: Python 3.14.10, PySide6 6.12.0 (Apple Silicon, macOS 27.0.1).

```bash
conda create -n tempbox -c conda-forge --override-channels python=3.14 pip
conda activate tempbox
pip install PySide6==6.12.0
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
- **Quit** with the window's **Quit** button (bottom right) or `Cmd+Q` while the
  window is focused. On macOS 27, Qt reports status item clicks without the mouse
  button information, so a right-click behaves like a normal click and the tray
  menu may not open on that macOS version.
- **Drag files from Finder** into the window (single or multiple files). Folders,
  symbolic links and other special files are rejected with a status message.
- Select a file and use **Open**, **Show in Finder** or **Restore**.
  - Restore puts the file back at its original path.
  - If the original folder is gone, or a file with the same name exists there,
    TempBox asks you to choose another folder. Existing files are never overwritten.
- Closing the window hides it; TempBox keeps running in the menu bar.

## Data location

```
~/Library/Application Support/TempBox/
├── files/<uuid>/<original-name>   # files managed by TempBox
├── records.json                   # metadata index (atomic writes)
└── .instance.lock                 # single-instance lock
```

TempBox only touches files the user drags in. Files are moved rather than copied,
original names and paths are kept in `records.json`, and a damaged index is moved
aside as `records.corrupt-*.json` instead of being deleted.

## Tests

```bash
conda activate tempbox
python -m unittest discover -s tests -t . -v
```

Storage tests need no GUI. Window tests use Qt's `offscreen` platform so they do not
open windows on the desktop. Menu bar clicks and real Finder drags are verified
manually (see the Phase 1 acceptance notes).

## Known limitations (Phase 1)

- No automatic expiry or clean-up yet (Phase 2).
- No search, sorting, batch operations or settings yet (Phase 3).
- English-only UI.
- Files are moved on the GUI thread, so moving very large files briefly freezes the
  window.
- TempBox runs without a Dock icon (accessory activation policy).
- On macOS 27 the Qt tray reports clicks as `Unknown`, so the right-click tray menu
  may not be available; quit from the window or with `Cmd+Q`.
- The menu bar icon is a template image and follows the light/dark menu bar.
