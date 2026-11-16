# TempBox v1.0.0 — Release Notes

**Temporary files deserve a temporary home.**

TempBox 1.0.0 is the first public macOS release. It is a menu bar app for files that
should not live on the Desktop forever: drag them into the floating panel, choose a
retention period, and they are moved to the macOS Trash automatically when they
expire.

## Download

- Asset: `TempBox-1.0.0-macOS-arm64.dmg`
- SHA-256: `4eaa943d6b67d4017aaf156a92959a3324c7abc99a07e7dc12d5ec3ac11534db` (also published as a `.sha256` file)
- System: macOS, Apple Silicon (arm64), tested on macOS 27.0.1
- Release page: <https://github.com/giaoWH/tempbox/releases/tag/v1.0.0>

## Highlights

- Compact menu bar panel with drag-and-drop import from Finder.
- Default and per-file retention; automatic Trash cleanup with startup catch-up.
- Search, sort, multi-select, batch restore and batch expiry changes.
- Pause/resume automatic cleanup with persistent state and backlog confirmation.
- Recently cleaned history (metadata only, up to 100 entries).
- Expiry reminders 10 minutes before a file is due.
- Finder Quick Action: Move to TempBox (install from Settings).
- Launch at login, light/dark appearance, single-instance protection.
- User-triggered Check for Updates via GitHub Releases; no automatic downloads.

## Installation

1. Download the DMG from the official GitHub Release.
2. Open it and drag TempBox.app to Applications.
3. If macOS blocks the first launch, do not disable Gatekeeper or SIP. Open System
   Settings → Privacy & Security, find TempBox and choose Open Anyway; alternatively
   Control-click the app and choose Open.
4. Look for the TempBox icon in the menu bar (there is no Dock icon).

**Unsigned build:** v1.0.0 is not Developer ID signed and is not notarized by Apple.
Gatekeeper may warn on first launch. Only download from the official repository and
verify the SHA-256 checksum. Apple Silicon only; no Intel build.

## Data and privacy

TempBox stores managed files under
`~/Library/Application Support/TempBox/`. Expired files are moved to the macOS Trash,
never permanently deleted by TempBox. No account, cloud service or telemetry is used.
The update check contacts the GitHub Releases API only when requested.

## Known limitations

- No Developer ID signature, Apple notarization or Intel build.
- The menu bar icon does not accept Finder file drops; use the floating panel.
- Quick Action installation may require reopening Finder or enabling the service under
  System Settings → Keyboard → Keyboard Shortcuts → Services.
- Notification delivery depends on macOS Notification Center permissions and the
  unsigned app launch mode.
- Check for Updates reports network/API errors; it does not download or install.
- No automatic update/replacement.

## License

TempBox source is licensed under the Apache License 2.0. Third-party components keep
their own licenses, including PySide6/Qt under the LGPL-3.0 option, Python under the
PSF license, Send2Trash under BSD-3-Clause, and the PyInstaller bootloader under
GPL-2.0 with the PyInstaller Bootloader Exception. See `THIRD_PARTY_LICENSES.md` and
the `licenses/` directory inside the DMG.

## Feedback

Report issues at <https://github.com/giaoWH/tempbox/issues>. Do not attach real
personal files to reports.
