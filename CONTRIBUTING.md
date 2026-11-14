# Contributing to TempBox

TempBox is a small macOS menu bar utility. Contributions are welcome once the project's
license is chosen; until then, please open an issue before sending substantial code.

## Before you start

- macOS + Conda environment as described in [README.md](README.md) and
  [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
- Run the test suite before and after changes:
  ```bash
  python -m unittest discover -s tests -t . -v
  ```
- Keep changes focused. This project deliberately avoids large frameworks and
  unnecessary abstractions.

## Scope and safety

- Do not change file deletion semantics. Expired managed files go to the macOS Trash,
  never permanent deletion.
- Preserve the storage format and backward compatibility; existing user data must
  continue to load.
- Never test with a real user's TempBox data or personal files. Use temporary
  directories and mocked Trash operations.
- Do not add a second file-management implementation. Reuse `FileStore`.
- Preserve the approved floating-panel UI and visual language.
- Do not add dependencies unless they are clearly necessary and discussed.

## What to include in a change

- A concise explanation of the user-visible behavior and any safety implications.
- Tests for real data-loss risks (import, conflicts, restore, cleanup, JSON persistence,
  pause/resume, history, reminders).
- Manual verification notes for macOS-only behavior (Finder, notifications, menu bar,
  Trash).
- Documentation updates if behavior, setup or architecture changes.

## Style

- Python 3.14, type annotations, standard library first.
- Keep functions focused and comments purposeful.
- Follow the existing module boundaries; avoid new tiny modules for single helpers.
- Do not commit caches, local environments, logs, `.DS_Store`, build outputs or user
  data. See `.gitignore`.

## License

No license has been selected yet. Contributions cannot be distributed under a public
license until the repository owner chooses one (MIT and Apache-2.0 are reasonable
candidates for a project of this size). Do not assume a license.
