"""Regression tests for the background GitHub release-check worker."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
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
            "assets": [
                {
                    "name": name,
                    "browser_download_url": (
                        "https://github.com/NaveedQamar1/Paisa-Laya/"
                        f"releases/download/{tag}/{name}"
                    ),
                }
                for name in asset_names
            ],
        }

    @staticmethod
    def download_response(data):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [data, b""]
        return response

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
            elif platform == "win32":
                with patch.object(app.platform_module, "machine", return_value=machine):
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


    def test_arm64_macos_selects_only_the_arm64_release_asset(self):
        asset_name = "SCAFA_Workforce_macOS_apple-silicon.zip"
        release = self.release("scafa-v1.5.0", (asset_name, "checksums.txt"))

        self.run_worker(release, platform="darwin", machine="arm64")

        self.assertEqual(
            self.window._pending_release,
            (release, asset_name, "macos"),
        )
        self.deliver_ui_callback()
        self.update_offer.assert_called_once_with("1.5.0")
        self.update_failed.assert_not_called()

    def test_unknown_macos_architecture_fails_closed(self):
        release = self.release(
            "scafa-v1.5.0",
            ("SCAFA_Workforce_macOS_intel.zip", "checksums.txt"),
        )

        self.run_worker(release, platform="darwin", machine="mips64")
        self.deliver_ui_callback()

        self.update_failed.assert_called_once()
        self.assertIn("macOS architecture", self.update_failed.call_args.args[0])
        self.update_offer.assert_not_called()
        self.assertFalse("_pending_release" in self.window.__dict__)

    def test_non_x64_windows_architecture_fails_closed(self):
        release = self.release(
            "scafa-v1.5.0",
            ("SCAFA_Workforce_Setup.exe", "checksums.txt"),
        )

        self.run_worker(release, platform="win32", machine="arm64")
        self.deliver_ui_callback()

        self.update_failed.assert_called_once()
        self.assertIn("Windows x64", self.update_failed.call_args.args[0])
        self.update_offer.assert_not_called()
        self.assertFalse("_pending_release" in self.window.__dict__)


    def test_external_release_asset_url_is_rejected_before_offer(self):
        release = self.release(
            "scafa-v1.5.0",
            ("SCAFA_Workforce_Setup.exe", "checksums.txt"),
        )
        release["assets"][0]["browser_download_url"] = (
            "https://updates.example.invalid/SCAFA_Workforce_Setup.exe"
        )

        self.run_worker(release)
        self.deliver_ui_callback()

        self.update_failed.assert_called_once()
        self.assertIn("expected GitHub repository release", self.update_failed.call_args.args[0])
        self.update_offer.assert_not_called()
        self.assertFalse("_pending_release" in self.window.__dict__)

    def test_release_asset_url_rejects_wrong_repository_and_query_string(self):
        valid = (
            "https://github.com/NaveedQamar1/Paisa-Laya/releases/download/"
            "scafa-v1.5.0/SCAFA_Workforce_Setup.exe"
        )
        invalid_urls = (
            "http://github.com/NaveedQamar1/Paisa-Laya/releases/download/scafa-v1.5.0/SCAFA_Workforce_Setup.exe",
            valid.replace("/NaveedQamar1/Paisa-Laya/", "/someone-else/other-repo/"),
            valid + "?redirect=https://example.invalid",
            valid.replace("github.com", "github.com.example.invalid"),
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaisesRegex(RuntimeError, "expected GitHub repository"):
                    app.validate_release_asset_url(
                        url, "scafa-v1.5.0", "SCAFA_Workforce_Setup.exe"
                    )

    def test_download_worker_verifies_and_stages_package_before_launch(self):
        package_bytes = b"verified test installer"
        digest = hashlib.sha256(package_bytes).hexdigest()
        asset_name = "SCAFA_Workforce_Setup.exe"
        release = self.release("scafa-v1.5.0", (asset_name, "checksums.txt"))
        release["assets"][0]["digest"] = "sha256:" + digest
        checksum_bytes = f"{digest}  {asset_name}\n".encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            install = root / "install"
            install.mkdir()
            executable = install / "SCAFA_Workforce.exe"
            helper = install / "scafa-updater.exe"
            helper.write_bytes(b"test updater helper")
            self.window._pending_release = (release, asset_name, "windows")

            with patch.object(app.Path, "home", return_value=home), patch.object(
                app.sys, "executable", str(executable)
            ), patch.object(
                app.urllib.request,
                "urlopen",
                side_effect=[
                    self.download_response(package_bytes),
                    self.download_response(checksum_bytes),
                ],
            ) as open_asset, patch.object(
                self.window, "_launch_update_helper"
            ) as launch_helper:
                self.window._download_and_prepare_update()
                self.window.after.assert_called_once()
                self.window.after.call_args.args[1]()

            self.assertEqual(open_asset.call_count, 2)
            staged = home / "SCAFAWorkforce" / "updates"
            self.assertEqual((staged / asset_name).read_bytes(), package_bytes)
            self.assertEqual((staged / "checksums.txt").read_bytes(), checksum_bytes)
            self.assertEqual(
                (staged / "scafa-updater-run.exe").read_bytes(),
                b"test updater helper",
            )
            launch_helper.assert_called_once()
            command = launch_helper.call_args.args[0]
            self.assertEqual(command[command.index("--platform") + 1], "windows")
            self.assertEqual(command[command.index("--package") + 1], str(staged / asset_name))

    def test_download_worker_removes_partial_files_when_checksum_transfer_fails(self):
        package_bytes = b"complete installer"
        asset_name = "SCAFA_Workforce_Setup.exe"
        release = self.release("scafa-v1.5.0", (asset_name, "checksums.txt"))

        partial_checksum = MagicMock()
        partial_checksum.__enter__.return_value = partial_checksum
        partial_checksum.read.side_effect = [
            b"partial checksum data",
            OSError("connection reset during checksum download"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            install = root / "install"
            install.mkdir()
            executable = install / "SCAFA_Workforce.exe"
            self.window._pending_release = (release, asset_name, "windows")

            with patch.object(app.Path, "home", return_value=home), patch.object(
                app.sys, "executable", str(executable)
            ), patch.object(
                app.urllib.request,
                "urlopen",
                side_effect=[
                    self.download_response(package_bytes),
                    partial_checksum,
                ],
            ) as open_asset:
                self.window._download_and_prepare_update()
                self.window.after.assert_called_once()
                self.window.after.call_args.args[1]()

            staged = home / "SCAFAWorkforce" / "updates"
            self.assertEqual(open_asset.call_count, 2)
            self.assertFalse((staged / asset_name).exists())
            self.assertFalse((staged / "checksums.txt").exists())
            self.assertFalse((staged / "scafa-updater-run.exe").exists())
            self.update_failed.assert_called_once()
            self.assertIn("connection reset", self.update_failed.call_args.args[0])


    def test_download_worker_rejects_checksum_mismatch_without_launching(self):
        package_bytes = b"tampered installer"
        wrong_digest = hashlib.sha256(b"original installer").hexdigest()
        asset_name = "SCAFA_Workforce_Setup.exe"
        release = self.release("scafa-v1.5.0", (asset_name, "checksums.txt"))
        release["assets"][0]["digest"] = "sha256:" + wrong_digest
        checksum_bytes = f"{wrong_digest}  {asset_name}\n".encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            install = root / "install"
            install.mkdir()
            executable = install / "SCAFA_Workforce.exe"
            self.window._pending_release = (release, asset_name, "windows")

            with patch.object(app.Path, "home", return_value=home), patch.object(
                app.sys, "executable", str(executable)
            ), patch.object(
                app.urllib.request,
                "urlopen",
                side_effect=[
                    self.download_response(package_bytes),
                    self.download_response(checksum_bytes),
                ],
            ), patch.object(self.window, "_launch_update_helper") as launch_helper:
                self.window._download_and_prepare_update()
                self.window.after.assert_called_once()
                self.window.after.call_args.args[1]()

            self.update_failed.assert_called_once()
            self.assertIn("failed SHA-256 verification", self.update_failed.call_args.args[0])
            self.assertFalse(
                (home / "SCAFAWorkforce" / "updates" / asset_name).exists()
            )
            launch_helper.assert_not_called()

    def test_download_worker_fails_closed_when_installed_helper_is_missing(self):
        package_bytes = b"verified test installer"
        digest = hashlib.sha256(package_bytes).hexdigest()
        asset_name = "SCAFA_Workforce_Setup.exe"
        release = self.release("scafa-v1.5.0", (asset_name, "checksums.txt"))
        release["assets"][0]["digest"] = "sha256:" + digest
        checksum_bytes = f"{digest}  {asset_name}\n".encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            install = root / "install"
            install.mkdir()
            executable = install / "SCAFA_Workforce.exe"
            self.window._pending_release = (release, asset_name, "windows")

            with patch.object(app.Path, "home", return_value=home), patch.object(
                app.sys, "executable", str(executable)
            ), patch.object(
                app.urllib.request,
                "urlopen",
                side_effect=[
                    self.download_response(package_bytes),
                    self.download_response(checksum_bytes),
                ],
            ), patch.object(self.window, "_launch_update_helper") as launch_helper:
                self.window._download_and_prepare_update()
                self.window.after.assert_called_once()
                self.window.after.call_args.args[1]()

            self.update_failed.assert_called_once()
            self.assertIn("update helper is missing", self.update_failed.call_args.args[0])
            launch_helper.assert_not_called()



if __name__ == "__main__":
    unittest.main()
