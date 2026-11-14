# TempBox User Guide

English | [简体中文](USAGE.zh-CN.md)

TempBox keeps temporary files out of the way and moves them to the macOS Trash when
their time is up. It runs as a menu bar app with a compact floating panel.

> This guide describes the current v0.5.0 development build. TempBox currently runs
> from a Conda environment; a packaged `.app` is planned for a later phase.

## Opening the panel

- Left-click the TempBox menu bar icon to show or hide the panel.
- The panel appears below the icon, takes focus, and hides when you click outside,
  press `Esc`, or press `Cmd+W`.
- TempBox has no Dock icon. Closing/hiding the panel does not quit the app.
- Quit from the panel footer, `Cmd+Q`, or the right-click menu on the menu bar icon.
  The right-click menu intentionally contains only **Quit TempBox**.

## Adding files

### Drag and drop

Drag one or more files from Finder into the panel. They are moved into TempBox's
storage, not copied. Folders, symbolic links and other non-regular files are rejected
with a status message.

New files use the current **default retention** (initially 1 day).

### Finder Quick Action

1. Open Settings (gear) → **Install Finder Quick Action**.
2. In Finder, select one or more regular files and right-click.
3. Choose **Quick Actions → Move to TempBox**. Depending on macOS, the item may be
   under **Services** instead.
4. Files appear in a running panel within about two seconds. If TempBox is not
   running, the Quick Action imports them directly and the next launch displays them.

The Quick Action uses the same import logic and the current default retention. It does
not open a file picker. If it is missing from Finder:

- reopen a Finder window, or relaunch Finder;
- check both **Quick Actions** and **Services** in the right-click menu;
- enable **Move to TempBox** under System Settings → Keyboard → Keyboard Shortcuts →
  Services (on some macOS versions: General → Login Items & Extensions).

Remove it from Settings when no longer needed.

> Dragging files onto the menu bar icon itself is not supported. Use the panel.

## Managing files

Each row shows a type icon, file name, size, and relative remaining time
(`7 days`, `35 min`, `Expired`, `Cleanup failed`, or `No expiration`). Hover to see
added and exact expiry times.

- **Open**: double-click a row, or use `···` → Open.
- **Show in Finder**: `···` → Show in Finder.
- **Restore**: `···` → Restore. TempBox moves the file back to its original path when
  that path is free. If a file with that name already exists, or the original folder
  is gone, TempBox asks you to choose a destination folder; it never overwrites an
  existing file.
- **Change expiry**: `···` → Change Expiration → preset (1 hour, 1 day, 7 days,
  30 days) or Custom…. Custom times must be in the future.
- **Search**: filters by file name.
- **Sort**: Added, Name, Size, Expires. Sorting and search do not modify files.
- **Select**: enters batch mode with checkboxes. Choose **Restore** or **Expiration**
  for the checked files. Batch restore is per-file: conflicts and missing originals
  are reported individually, and successful files still restore.
- **Header**: file count and total size.
- **Footer**: status, pause indicator, default retention, History, Quit.

## Retention and automatic cleanup

The default retention applies to new imports only; changing it does not re-date
existing files. Each file has its own expiry time.

While TempBox runs, it checks for expired files every 30 seconds. At startup it also
runs an overdue cleanup (unless automatic cleanup is paused). Expired files are moved
to the macOS Trash; TempBox never permanently deletes managed files.

If moving a file to the Trash fails, the file and its record remain in TempBox, the row
shows **Cleanup failed** with a tooltip, and TempBox retries on later checks. A record
whose stored file is missing is reported but never treated as successfully cleaned.
Files without an expiry (for example, old Phase 1 records) are never automatically
cleaned.

When TempBox is not running, no cleanup happens. Expired files are handled at the next
launch unless cleanup is paused.

## Pause and resume automatic cleanup

Settings → **Pause automatic cleanup**, or the persistent paused state stored from a
previous run.

While paused:

- imports, open, restore and expiry changes still work;
- expiry times continue counting down;
- no automatic cleanup runs, including on startup;
- the panel footer shows **Cleanup paused** and a paused status.

Resuming checks for overdue files. If there are any, TempBox shows the number and asks
whether to move them to the Trash now. Choosing **No** leaves automatic cleanup paused
(the setting is written back), so the timer cannot clean the backlog without a fresh
confirmation. Quit and relaunch while paused and TempBox starts paused.

## Recently cleaned history

Footer → **History** lists the most recent successful expiry cleanups (up to 100):

- original name and path;
- size;
- added time, expiry time and actual cleanup time.

Failed cleanups are not recorded. Files you restore manually are not cleanup events.
**Clear History** only clears this metadata; it does not delete anything from the
system Trash. TempBox cannot automatically restore files from the Trash; the history
is for locating what happened.

## Expiry reminders

When enabled (default), TempBox sends at most one notification per file and expiry
cycle when the file is within 10 minutes of expiry. Several files due soon are combined
into one notification. Changing a file's expiry starts a new cycle. Turn reminders off
in Settings.

Reminders are checked while TempBox is running (at startup and on the periodic check).
They are not sent while the app is quit. Notification delivery depends on macOS
Notification Center permissions and the development-script launch mode; if notifications
do not appear, cleanup still behaves normally. Reminder state is kept in memory for the
current run; a restart may produce one reminder again for the same cycle.

## Settings

The gear opens settings for:

- **Default retention for new files** — applies to future imports only.
- **Launch TempBox at login** — writes a per-user LaunchAgent that starts the app
  hidden. If you move the Python environment or project, toggle this off/on again.
- **Pause automatic cleanup** — see above.
- **Remind me 10 minutes before expiry** — reminder toggle.
- **Finder Quick Action** — install/remove.
- **About TempBox** — current version and **Check for Updates…**. Update checking is
  not enabled in this development version; the dialog says so explicitly and performs
  no network request.

## Update checks

The current build exposes only the update-check interface. No background network
requests are made, and the app never claims it is up to date. GitHub Releases support
is planned for Phase 5.

## Where files live

```
~/Library/Application Support/TempBox/
├── files/<uuid>/<original-name>
├── records.json
├── history.json
├── settings.json
├── .instance.lock
└── .data.lock
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for metadata details. Do not edit these files
while TempBox is running unless you know what you are doing; back up the folder before
manual changes.

## Troubleshooting

- **App is already running**: TempBox allows one instance per data directory. Use the
  running menu bar icon.
- **Panel is hidden**: click the menu bar icon, or use the app again. It does not show
  in the Dock by design.
- **A restore failed**: the original folder may be gone or a file with the same name
  exists; choose another destination.
- **Quick Action missing**: see the install section above; Finder caches service menus
  aggressively.
- **No reminder notification**: check System Settings → Notifications for TempBox/Python
  and whether reminders are enabled; the development script mode may limit delivery.
- **Login launch stopped working**: re-toggle Launch at login after moving the project
  or Python environment.
