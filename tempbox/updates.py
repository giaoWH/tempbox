"""Interface boundary for future update checking (GitHub Releases in Phase 5).

This development build intentionally performs no network requests and never
claims that the app is up to date.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import __version__

# Filled in when the public release repository is defined in Phase 5.
RELEASES_URL: str | None = None


@dataclass(frozen=True)
class UpdateStatus:
    state: str  # not_configured | up_to_date | update_available | error
    message: str


def current_version() -> str:
    return __version__


def check_for_updates() -> UpdateStatus:
    return UpdateStatus(
        state="not_configured",
        message=(
            "Update checking is not enabled in this development build yet. "
            "A future version will check GitHub Releases."
        ),
    )


def open_release_page() -> bool:
    """Reserved for Phase 5; returns False while no release URL is configured."""
    return False
