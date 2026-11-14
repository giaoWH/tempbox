"""Tests for the update-check interface boundary."""

from __future__ import annotations

import unittest

from tempbox import __version__
from tempbox import updates


class UpdateCheckerTest(unittest.TestCase):
    def test_current_version_comes_from_project_metadata(self) -> None:
        self.assertEqual(updates.current_version(), __version__)
        self.assertTrue(updates.current_version().startswith("0.5"))

    def test_check_is_not_configured_and_does_not_claim_up_to_date(self) -> None:
        status = updates.check_for_updates()

        self.assertEqual(status.state, "not_configured")
        self.assertIn("not enabled", status.message)
        self.assertNotIn("up to date", status.message.lower())

    def test_no_release_page_is_configured_yet(self) -> None:
        self.assertIsNone(updates.RELEASES_URL)
        self.assertFalse(updates.open_release_page())


if __name__ == "__main__":
    unittest.main()
