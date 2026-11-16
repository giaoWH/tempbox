"""Entry point for TempBox.

Run the app with ``python main.py``. The packaged app uses the same entry point;
``--quick-action`` is a headless helper invoked by the Finder Quick Action.
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--quick-action":
        from tempbox.quick_action import main as quick_action_main

        return quick_action_main(sys.argv[2:])

    from tempbox.app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
