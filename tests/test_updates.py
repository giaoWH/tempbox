"""Tests for GitHub Releases update checking (no network access)."""

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest import mock

from tempbox import __version__, updates


class FakeResponse:
    def __init__(self, payload) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


def opener(payload=None, error=None):
    def open_url(request, timeout):
        if error is not None:
            raise error
        return FakeResponse(payload)

    return open_url


class UpdateCheckerTest(unittest.TestCase):
    def test_current_version_comes_from_project_metadata(self) -> None:
        self.assertEqual(updates.current_version(), __version__)
        self.assertTrue(updates.current_version().startswith("1.0"))

    def test_up_to_date(self) -> None:
        status = updates.check_for_updates(
            current="1.0.0",
            opener=opener(
                {
                    "tag_name": "v1.0.0",
                    "html_url": "https://github.com/giaoWH/tempbox/releases/tag/v1.0.0",
                    "body": "- First release",
                }
            ),
        )

        self.assertEqual(status.state, "up_to_date")
        self.assertIn("up to date", status.message)

    def test_update_available_includes_version_notes_and_url(self) -> None:
        status = updates.check_for_updates(
            current="1.0.0",
            opener=opener(
                {
                    "tag_name": "v1.0.1",
                    "html_url": "https://github.com/giaoWH/tempbox/releases/tag/v1.0.1",
                    "body": "- Fixed something important",
                }
            ),
        )

        self.assertEqual(status.state, "update_available")
        self.assertEqual(status.latest_version, "1.0.1")
        self.assertIn("Fixed something important", status.release_notes)
        self.assertEqual(
            status.release_url,
            "https://github.com/giaoWH/tempbox/releases/tag/v1.0.1",
        )

    def test_missing_release_is_not_reported_as_up_to_date(self) -> None:
        error = urllib.error.HTTPError(
            updates.LATEST_RELEASE_API, 404, "Not Found", None, None
        )

        try:
            status = updates.check_for_updates(opener=opener(error=error))
        finally:
            error.close()

        self.assertEqual(status.state, "no_release")
        self.assertNotIn("up to date", status.message.lower())
        self.assertEqual(status.release_url, updates.RELEASES_URL)

    def test_rate_limit_is_reported(self) -> None:
        error = urllib.error.HTTPError(
            updates.LATEST_RELEASE_API, 403, "Forbidden", None, None
        )

        try:
            status = updates.check_for_updates(opener=opener(error=error))
        finally:
            error.close()

        self.assertEqual(status.state, "api_error")
        self.assertIn("rate-limited", status.message)

    def test_network_failure_is_reported(self) -> None:
        status = updates.check_for_updates(
            opener=opener(error=urllib.error.URLError("offline"))
        )

        self.assertEqual(status.state, "network_error")
        self.assertIn("Could not reach GitHub", status.message)

    def test_invalid_release_metadata_is_reported(self) -> None:
        status = updates.check_for_updates(
            opener=opener({"tag_name": "not-a-version", "html_url": "bad"})
        )

        self.assertEqual(status.state, "api_error")
        self.assertNotIn("up to date", status.message.lower())

    def test_unrecognized_release_url_falls_back_to_release_page(self) -> None:
        status = updates.check_for_updates(
            current="1.0.0",
            opener=opener(
                {
                    "tag_name": "v1.1.0",
                    "html_url": "https://example.invalid/fake",
                    "body": "notes",
                }
            ),
        )

        self.assertEqual(status.state, "update_available")
        self.assertEqual(status.release_url, updates.RELEASES_URL)


if __name__ == "__main__":
    unittest.main()
