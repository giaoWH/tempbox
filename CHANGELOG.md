# Changelog

English | [简体中文](CHANGELOG.zh-CN.md)

TempBox is still pre-release. Version headings below describe development phases; no
GitHub Releases or installable `.app` builds exist yet.

## v0.5.0 — Phase 4.5 (unreleased)

Engineering cleanup and release preparation.

- Split secondary windows (expiry picker, Settings, History) out of `window.py` into
  `dialogs.py`.
- Moved shared display formatting into `formatting.py`; removed the duplicate
  `format_size` implementation from the theme module.
- Centralized the TempBox data-directory location in `paths.py`.
- Removed unused imports and development-only prototype files from the repository.
- Organized screenshots under `docs/` and expanded `.gitignore`.
- Optimized external index refresh so the app only takes the cross-process lock when
  `records.json` actually changed.
- Added user, developer and contribution documentation plus this changelog.
- Bumped the development version to 0.5.0.

## v0.4.0 — Phase 4 (unreleased)

Advanced features and macOS integration.

- Finder Quick Action **Move to TempBox**, with install/remove from Settings and
  automatic macOS Services refresh.
- Recent cleanup history (metadata only, 100 entries, clearable).
- Persistent pause/resume for automatic cleanup, including startup behavior and
  resume confirmation for overdue files.
- Expiry reminders 10 minutes before a file is due, with combined notifications,
  settings toggle and one-per-cycle behavior.
- Reserved update-check interface and About section showing the current version.
- Cross-process index locking/reload so the app and Quick Action helper can both
  import safely.
- Fixed the menu bar Quit behavior leaving a stale status item until the next click.

## v0.3.5 — Phase 3.5 (unreleased)

- Replaced the table-style window with the approved compact floating panel.
- Added custom file rows, search/sort controls, selection mode, batch actions,
  light/dark theme support and menu bar positioning.
- Preserved existing import, restore, retention and cleanup behavior.

## v0.3.0 — Phase 3 (unreleased)

- Search, sorting, multi-file selection, batch restore and batch expiry changes.
- Settings for default retention and launch at login.
- Auto-hide on focus loss and menu bar/tray focus handling.
- More polished status messages and error reporting.

## v0.2.0 — Phase 2 (unreleased)

- Per-file expiry and automatic cleanup to the macOS Trash.
- Retention presets and custom expiry dates.
- JSON schema v2 with `expires_at`/`trash_error`; version 1 compatibility.
- Startup cleanup and failed-cleanup retries.

## v0.1.0 — Phase 1 (unreleased)

- Menu bar app with a basic file window.
- Drag-and-drop import into TempBox-managed storage.
- Open, reveal in Finder and restore files.
- Metadata persistence and single-instance locking.
