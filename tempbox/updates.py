"""GitHub Releases update checking.

The check is user-triggered and performed in a worker thread by the Settings UI.
It uses the GitHub Releases API for the public repository and never downloads or
installs an update automatically.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from . import __version__

# Confirmed from the repository remote (git remote -v):
# https://github.com/giaoWH/tempbox.git
REPOSITORY_URL = "https://github.com/giaoWH/tempbox"
RELEASES_URL = f"{REPOSITORY_URL}/releases"
LATEST_RELEASE_API = f"https://api.github.com/repos/giaoWH/tempbox/releases/latest"
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = f"TempBox/{__version__}"

Opener = Callable[..., Any]


@dataclass(frozen=True)
class UpdateStatus:
    state: str  # up_to_date | update_available | no_release | network_error | api_error
    message: str
    latest_version: str | None = None
    release_url: str | None = None
    release_notes: str | None = None


def current_version() -> str:
    return __version__


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _request() -> urllib.request.Request:
    return urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )


def _api_error(message: str) -> UpdateStatus:
    return UpdateStatus("api_error", message)


def _valid_release_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if value.startswith(REPOSITORY_URL + "/releases/"):
        return value
    return None


def check_for_updates(
    current: str = __version__,
    opener: Opener | None = None,
) -> UpdateStatus:
    """Query the latest stable GitHub Release and compare it with current.

    ``opener`` is injectable for tests; production uses urllib's default opener.
    Network and API failures are returned as statuses rather than raised, so a
    failed check can never affect the app's file handling.
    """
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(_request(), timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return UpdateStatus(
                "no_release",
                "No public release has been published yet.",
                release_url=RELEASES_URL,
            )
        if exc.code in (403, 429):
            return _api_error(
                "GitHub temporarily rate-limited the update check. "
                "Try again later or open the Releases page."
            )
        return _api_error(f"GitHub returned HTTP {exc.code} while checking for updates.")
    except (urllib.error.URLError, TimeoutError, OSError):
        return UpdateStatus(
            "network_error",
            "Could not reach GitHub. Check your network connection and try again.",
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return _api_error("GitHub returned an unreadable release response.")

    if not isinstance(payload, dict):
        return _api_error("GitHub returned an unexpected release response.")

    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        return _api_error("The latest release has no valid version tag.")
    latest = tag.strip().lstrip("v")
    latest_tuple = _version_tuple(latest)
    current_tuple = _version_tuple(current)
    if latest_tuple is None or current_tuple is None:
        return _api_error("The release version or current version is not valid.")

    release_url = _valid_release_url(payload.get("html_url")) or RELEASES_URL
    notes = payload.get("body")
    if not isinstance(notes, str):
        notes = ""
    notes = notes.strip()
    if len(notes) > 600:
        notes = notes[:597].rstrip() + "..."

    if latest_tuple > current_tuple:
        message = f"TempBox {latest} is available (you have {current})."
        return UpdateStatus(
            "update_available",
            message,
            latest_version=latest,
            release_url=release_url,
            release_notes=notes or None,
        )
    return UpdateStatus(
        "up_to_date",
        f"TempBox {current} is up to date.",
        latest_version=latest,
    )
