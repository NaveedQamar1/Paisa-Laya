"""Regression tests for the background GitHub release-check worker."""

import json
import unittest
from unittest.mock import MagicMock, Mock, patch

import app


class UpdateCheckWorkerTests(unittest.TestCase):
    """Exercise the real worker closure without starting a GUI or network request."""

    def setUp(self):
        self.window = object.__new__(app.App)
        self.window.status = Mock()
        self.window.after = Mock()

        self.thread_patch = patch.object(app.threading, "Thread")
        self.thread_class = self.thread_patch.start()
        self.addCleanup(self.thread_patch.stop)

        self.offer_patch = patch.object(self.window, "_update_offer")
        self.update_offer = self.offer_patch.start()
        self.addCleanup(self.offer_patch.stop)

        self.failure_patch = patch.object(self.window, "_update_check_failed")
        self.update_failed = self.failure_patch.start()
        self.addCleanup(self.failure_patch.stop)

        self.no_update_patch = patch.object(self.window, "_update_no_update")
        self.update_no_update = self.no_update_patch.start()
        self.addCleanup(self.no_update_patch.stop)

    @staticmethod
    def release(tag, asset_names):
        return {
            "tag_name": tag,
            "assets": [{"name": name} for name in asset_names],
        }

    def run_worker(self, release, platform="win32", machine="x86_64"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(release).encode("utf-8")

        with patch.object(
            app.urllib.request, "urlopen", return_value=response
        ) as open_release, patch.object(app.sys, "platform", platform):
            if platform == "darwin":
                with patch.object(
                    app.os, "uname", return_value=Mock(machine=machine), create=True
                ):
                    self.window.check_for_updates()
                    target = self.thread_class.call_args.kwargs["target"]
                    target()
            else:
                self.window.check_for_updates()
                target = self.thread_class.call_args.kwargs["target"]
                target()

        open_release.assert_called_once()
        self.thread_class.assert_called_once()
        self.thread_class.return_value.start.assert_called_once_with()

    def deliver_ui_callback(self):
        self.window.after.assert_called_once()
        delay, callback = self.window.after.call_args.args
        self.assertEqual(delay, 0)
        callback()

    def test_malformed_release_tag_never_reaches_update_offer(self):
        release = self.release(
            "scafa-v1.5.0-rc1",
            ("SCAFA_Workforce_Setup.exe", "checksums.txt"),
        )

        self.run_worker(release)
        self.deliver_ui_callback()

        self.update_failed.assert_called_once()
        self.assertIn("invalid SCAFA version tag", self.update_failed.call_args.args[0])
        self.update_offer.assert_not_called()
        self.assertFalse("_pending_release" in self.window.__dict__)

    def test_windows_selects_setup_exe_and_requires_checksum_manifest(self):
        release = self.release(
            "scafa-v1.5.0",
            ("SCAFA_Workforce_Setup.exe", "checksums.txt"),
        )

        self.run_worker(release, platform="win32")

        self.assertEqual(
            self.window._pending_release,
            (release, "SCAFA_Workforce_Setup.exe", "windows"),
        )
        self.deliver_ui_callback()
        self.update_offer.assert_called_once_with("1.5.0")
        self.update_failed.assert_not_called()

    def test_intel_macos_selects_intel_zip_and_requires_checksum_manifest(self):
        release = self.release(
            "scafa-v1.5.0",
            ("SCAFA_Workforce_macOS_intel.zip", "checksums.txt"),
        )

        self.run_worker(release, platform="darwin", machine="x86_64")

        self.assertEqual(
            self.window._pending_release,
            (release, "SCAFA_Workforce_macOS_intel.zip", "macos"),
        )
        self.deliver_ui_callback()
        self.update_offer.assert_called_once_with("1.5.0")
        self.update_failed.assert_not_called()

    def test_missing_platform_package_or_checksum_manifest_fails_closed(self):
        invalid_asset_sets = (
            ("SCAFA_Workforce_Setup.exe",),
            ("checksums.txt",),
        )

        for asset_names in invalid_asset_sets:
            with self.subTest(asset_names=asset_names):
                self.window.after.reset_mock()
                self.update_failed.reset_mock()
                self.update_offer.reset_mock()
                self.thread_class.reset_mock()

                release = self.release("scafa-v1.5.0", asset_names)
                self.run_worker(release, platform="win32")
                self.deliver_ui_callback()

                self.update_failed.assert_called_once()
                self.assertIn("missing", self.update_failed.call_args.args[0])
                self.update_offer.assert_not_called()
                self.assertFalse("_pending_release" in self.window.__dict__)

    def test_equal_or_older_release_does_not_offer_an_update(self):
        release = self.release(
            "scafa-v1.4.0",
            ("SCAFA_Workforce_Setup.exe", "checksums.txt"),
        )

        self.run_worker(release, platform="win32")
        self.deliver_ui_callback()

        self.update_no_update.assert_called_once_with("1.4.0")
        self.update_offer.assert_not_called()
        self.update_failed.assert_not_called()
        self.assertFalse("_pending_release" in self.window.__dict__)


if __name__ == "__main__":
    unittest.main()
