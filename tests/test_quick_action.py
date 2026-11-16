"""Tests for the Finder Quick Action bundle and import helper."""

from __future__ import annotations

import os
import plistlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tempbox import quick_action
from tempbox.settings import AppSettings
from tempbox.storage import FileStore


class QuickActionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tempbox-quickaction-test-")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self._refresh_patch = mock.patch("tempbox.quick_action._refresh_services")
        self.refresh_services = self._refresh_patch.start()
        self.addCleanup(self._refresh_patch.stop)

    def test_install_writes_a_finder_service_workflow(self) -> None:
        workflow = quick_action.install(home=self.home)

        contents = workflow / "Contents"
        self.assertTrue((contents / "Info.plist").is_file())
        self.assertTrue((contents / "Resources" / "document.wflow").is_file())
        self.assertTrue(quick_action.is_installed(home=self.home))
        self.refresh_services.assert_called_once()

        info = plistlib.loads((contents / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleName"], "Move to TempBox")
        service = info["NSServices"][0]
        self.assertEqual(service["NSMessage"], "runWorkflowAsService")
        self.assertEqual(
            service["NSRequiredContext"]["NSApplicationIdentifier"],
            "com.apple.finder",
        )
        self.assertIn("public.item", service["NSSendFileTypes"])

        document = plistlib.loads(
            (contents / "Resources" / "document.wflow").read_bytes()
        )
        metadata = document["workflowMetaData"]
        self.assertEqual(
            metadata["workflowTypeIdentifier"], "com.apple.Automator.servicesMenu"
        )
        self.assertEqual(
            metadata["serviceInputTypeIdentifier"],
            "com.apple.Automator.fileSystemObject",
        )
        self.assertEqual(metadata["serviceProcessesInput"], 1)
        self.assertEqual(metadata["presentationMode"], 15)
        self.assertEqual(metadata["applicationBundleID"], "com.apple.finder")
        action = document["actions"][0]["action"]
        self.assertEqual(
            action["ActionBundlePath"],
            "/System/Library/Automator/Run Shell Script.action",
        )
        self.assertEqual(action["ActionParameters"]["inputMethod"], 1)
        self.assertIn("tempbox.quick_action", action["ActionParameters"]["COMMAND_STRING"])
        self.assertIn(
            str(Path(quick_action.__file__).resolve().parent.parent),
            action["ActionParameters"]["COMMAND_STRING"],
        )

    def test_install_is_idempotent_and_uninstall_removes_it(self) -> None:
        quick_action.install(home=self.home)
        quick_action.install(home=self.home)
        self.assertTrue(quick_action.is_installed(home=self.home))

        self.assertTrue(quick_action.uninstall(home=self.home))
        self.assertFalse(quick_action.is_installed(home=self.home))
        self.assertFalse(quick_action.uninstall(home=self.home))

    def test_import_paths_moves_files_with_default_retention(self) -> None:
        root = self.base / "data"
        AppSettings(default_retention=timedelta(hours=1)).save(root)
        sources = []
        for name in ("one.txt", "two.txt"):
            source = self.base / name
            source.write_text(name, encoding="utf-8")
            sources.append(source)

        result = quick_action.import_paths(sources, root=root)

        self.assertEqual(len(result.added), 2)
        self.assertEqual(result.failed, [])
        self.assertFalse(any(source.exists() for source in sources))
        store = FileStore(root)
        store.load()
        self.assertEqual(len(store.list_files()), 2)
        for record in store.list_files():
            expires_at = datetime.fromisoformat(record.expires_at)
            self.assertGreaterEqual(
                expires_at, datetime.now(timezone.utc) + timedelta(minutes=59)
            )
            self.assertLessEqual(
                expires_at, datetime.now(timezone.utc) + timedelta(hours=1, minutes=1)
            )

    def test_two_store_instances_merge_and_refresh(self) -> None:
        root = self.base / "shared-data"
        first_store = FileStore(root)
        first_store.load()
        second_store = FileStore(root)
        second_store.load()
        first_source = self.base / "first.txt"
        second_source = self.base / "second.txt"
        first_source.write_text("first", encoding="utf-8")
        second_source.write_text("second", encoding="utf-8")

        first_store.import_files([first_source])
        second_store.import_files([second_source])

        self.assertTrue(first_store.refresh_from_disk())
        names = {record.original_name for record in first_store.list_files()}
        self.assertEqual(names, {"first.txt", "second.txt"})
        self.assertFalse(first_store.refresh_from_disk())

    def test_import_paths_safely_rejects_a_folder(self) -> None:
        root = self.base / "data"
        folder = self.base / "not-a-file"
        folder.mkdir()

        result = quick_action.import_paths([folder], root=root)

        self.assertEqual(result.added, [])
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(folder.is_dir())
        self.assertFalse((root / "records.json").exists() and FileStore(root).load())

    def test_main_honors_data_dir_override(self) -> None:
        root = self.base / "override-data"
        source = self.base / "from-finder.txt"
        source.write_text("finder", encoding="utf-8")
        env = {"TEMPBOX_DATA_DIR": str(root)}

        with mock.patch.dict(os.environ, env):
            exit_code = quick_action.main([str(source)])

        self.assertEqual(exit_code, 0)
        self.assertFalse(source.exists())
        store = FileStore(root)
        store.load()
        self.assertEqual(len(store.list_files()), 1)

    def test_shell_command_quotes_paths_with_spaces(self) -> None:
        command = quick_action.shell_command(
            project_root="/tmp/TempBox Project", python="/tmp/Python Bin/python"
        )

        self.assertIn("'/tmp/TempBox Project'", command)
        self.assertIn("'/tmp/Python Bin/python'", command)
        self.assertIn('-m tempbox.quick_action "$@"', command)


    def test_frozen_app_quick_action_uses_bundle_binary(self) -> None:
        app_binary = "/Applications/TempBox.app/Contents/MacOS/TempBox"
        with mock.patch.object(
            quick_action.sys, "frozen", True, create=True
        ), mock.patch.object(quick_action.sys, "executable", app_binary):
            command = quick_action.shell_command()

        self.assertEqual(command, f"{app_binary} --quick-action \"$@\"")


class RefreshServicesTest(unittest.TestCase):
    def test_refresh_services_failure_is_non_fatal(self) -> None:
        with mock.patch(
            "tempbox.quick_action.subprocess.run", side_effect=OSError("no pbs")
        ):
            self.assertFalse(quick_action._refresh_services())


if __name__ == "__main__":
    unittest.main()
