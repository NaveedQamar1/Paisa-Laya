import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater
import app


class UpdaterHelperTests(unittest.TestCase):
    def test_wait_for_already_exited_process_returns(self):
        with patch.object(updater.os, "kill", side_effect=ProcessLookupError):
            updater.wait_for_process(99999999, timeout=0.1)

    def test_windows_update_runs_installer_and_relaunches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            installer=root/"setup.exe"
            installer.write_text("installer")
            executable=root/"SCAFA_Workforce.exe"
            executable.write_text("application")
            with patch.object(
                updater.subprocess,
                "run",
                side_effect=[
                    unittest.mock.Mock(returncode=0, stdout="NOT_RUNNING\n", stderr=""),
                    unittest.mock.Mock(returncode=0),
                ],
            ) as run, patch.object(updater.subprocess,"Popen") as launch:
                updater.apply_windows(installer,root)
            self.assertEqual(run.call_count, 2)
            self.assertIn("Get-ScheduledTask", run.call_args_list[0].args[0][-1])
            self.assertEqual(run.call_args_list[1].args[0][0], str(installer))
            launch.assert_called_once_with([str(executable)],cwd=str(root))

    def test_windows_update_stops_and_restarts_a_running_monitor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            installer=root/"setup.exe"
            installer.write_text("installer")
            executable=root/"SCAFA_Workforce.exe"
            executable.write_text("application")
            with patch.object(
                updater.subprocess,
                "run",
                side_effect=[
                    unittest.mock.Mock(returncode=0, stdout="RUNNING\n", stderr=""),
                    unittest.mock.Mock(returncode=0),
                    unittest.mock.Mock(returncode=0, stdout="STARTED\n", stderr=""),
                ],
            ) as run, patch.object(updater.subprocess,"Popen") as launch:
                updater.apply_windows(installer,root)
            self.assertEqual(run.call_count, 3)
            self.assertIn("Stop-ScheduledTask", run.call_args_list[0].args[0][-1])
            self.assertEqual(run.call_args_list[1].args[0][0], str(installer))
            self.assertIn("Start-ScheduledTask", run.call_args_list[2].args[0][-1])
            launch.assert_called_once_with([str(executable)],cwd=str(root))

    def test_windows_update_restarts_monitor_when_installer_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            installer=root/"setup.exe"
            installer.write_text("installer")
            with patch.object(
                updater.subprocess,
                "run",
                side_effect=[
                    unittest.mock.Mock(returncode=0, stdout="RUNNING\n", stderr=""),
                    unittest.mock.Mock(returncode=5),
                    unittest.mock.Mock(returncode=0, stdout="STARTED\n", stderr=""),
                ],
            ) as run, patch.object(updater.subprocess,"Popen") as launch:
                with self.assertRaisesRegex(RuntimeError, "exit code 5"):
                    updater.apply_windows(installer,root)
            self.assertEqual(run.call_count, 3)
            self.assertIn("Start-ScheduledTask", run.call_args_list[2].args[0][-1])
            launch.assert_not_called()

    def test_windows_update_aborts_if_running_monitor_cannot_be_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            installer=root/"setup.exe"
            installer.write_text("installer")
            with patch.object(
                updater.subprocess,
                "run",
                return_value=unittest.mock.Mock(
                    returncode=1, stdout="", stderr="Access is denied."
                ),
            ) as run, patch.object(updater.subprocess,"Popen") as launch:
                with self.assertRaisesRegex(RuntimeError, "Could not stop"):
                    updater.apply_windows(installer,root)
            run.assert_called_once()
            launch.assert_not_called()

    def test_zip_extraction_rejects_parent_directory_paths(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            archive=root/"unsafe.zip"
            with zipfile.ZipFile(archive,"w") as zf:
                zf.writestr("../outside.txt","unsafe")
                zf.writestr("..\\\\outside-windows.txt","unsafe")
            with self.assertRaises(RuntimeError):
                updater.safe_extract_zip(archive,root/"extract")

    def test_zip_extraction_preserves_executable_permissions(self):
        import os
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            archive=root/"app.zip"
            info=zipfile.ZipInfo("SCAFA_Workforce.app/Contents/MacOS/SCAFA_Workforce")
            info.create_system=3
            info.external_attr=(0o100755 << 16)
            with zipfile.ZipFile(archive,"w") as zf:
                zf.writestr(info,b"executable")
            destination=root/"extracted"
            updater.safe_extract_zip(archive,destination)
            extracted=destination/info.filename
            if os.name!="nt":
                self.assertTrue(extracted.stat().st_mode & 0o111)

    def test_zip_extraction_rejects_symlinks(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            archive=root/"symlink.zip"
            info=zipfile.ZipInfo("SCAFA_Workforce.app/link")
            info.create_system=3
            info.external_attr=(0o120777 << 16)
            with zipfile.ZipFile(archive,"w") as zf:
                zf.writestr(info,"/tmp/outside")
            with self.assertRaises(RuntimeError):
                updater.safe_extract_zip(archive,root/"extracted")

    def test_zip_extraction_rejects_relative_symlink_escape(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "relative-escape.zip"
            info = zipfile.ZipInfo("SCAFA_Workforce.app/Contents/Resources/escape")
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(info, "../../../../outside")
            with self.assertRaisesRegex(RuntimeError, "outside its extraction folder"):
                updater.safe_extract_zip(archive, root / "extract")

    def test_macos_update_replaces_bundle_and_relaunches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            installed=root/"SCAFA_Workforce.app"
            (installed/"Contents"/"MacOS").mkdir(parents=True)
            (installed/"Contents"/"MacOS"/"SCAFA_Workforce").write_text("old")
            source=root/"package"/"SCAFA_Workforce.app"
            (source/"Contents"/"MacOS").mkdir(parents=True)
            (source/"Contents"/"MacOS"/"SCAFA_Workforce").write_text("new")
            archive=root/"update.zip"
            import zipfile
            with zipfile.ZipFile(archive,"w") as zf:
                for path in source.rglob("*"):
                    if path.is_file():
                        zf.write(path,path.relative_to(source.parent))
            with patch.object(updater.subprocess,"run",return_value=unittest.mock.Mock(returncode=0)) as launch:
                updater.apply_macos(archive,installed)
            self.assertEqual((installed/"Contents"/"MacOS"/"SCAFA_Workforce").read_text(),"new")
            launch.assert_called_once_with(["/usr/bin/open",str(installed)],check=True)

    def test_macos_launch_failure_restores_previous_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            installed=root/"SCAFA_Workforce.app"
            (installed/"Contents"/"MacOS").mkdir(parents=True)
            old_exe=installed/"Contents"/"MacOS"/"SCAFA_Workforce"
            old_exe.write_text("old")
            source=root/"package"/"SCAFA_Workforce.app"
            (source/"Contents"/"MacOS").mkdir(parents=True)
            (source/"Contents"/"MacOS"/"SCAFA_Workforce").write_text("new")
            archive=root/"update.zip"
            import zipfile
            with zipfile.ZipFile(archive,"w") as zf:
                for path in source.rglob("*"):
                    if path.is_file():
                        zf.write(path,path.relative_to(source.parent))
            with patch.object(updater.subprocess,"run",side_effect=OSError("launch failed")):
                with self.assertRaises(OSError):
                    updater.apply_macos(archive,installed)
            self.assertEqual(old_exe.read_text(),"old")


    @unittest.skipIf(os.name == "nt", "Windows runners may not permit symbolic-link creation")
    def test_zip_extraction_preserves_safe_relative_framework_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "framework.zip"
            current = zipfile.ZipInfo(
                "SCAFA_Workforce.app/Contents/Frameworks/Python.framework/Versions/Current"
            )
            current.create_system = 3
            current.external_attr = (stat.S_IFLNK | 0o777) << 16
            python_link = zipfile.ZipInfo(
                "SCAFA_Workforce.app/Contents/Frameworks/Python.framework/Python"
            )
            python_link.create_system = 3
            python_link.external_attr = (stat.S_IFLNK | 0o777) << 16
            runtime = zipfile.ZipInfo(
                "SCAFA_Workforce.app/Contents/Frameworks/Python.framework/Versions/3.12/Python"
            )
            runtime.create_system = 3
            runtime.external_attr = (stat.S_IFREG | 0o755) << 16

            with zipfile.ZipFile(archive, "w") as zf:
                # Put links before their targets to verify extraction is order-independent.
                zf.writestr(current, "3.12")
                zf.writestr(python_link, "Versions/Current/Python")
                zf.writestr(runtime, b"python-runtime")

            destination = root / "extracted"
            updater.safe_extract_zip(archive, destination)

            current_path = destination / current.filename
            python_path = destination / python_link.filename
            self.assertTrue(current_path.is_symlink())
            self.assertEqual(os.readlink(current_path), "3.12")
            self.assertTrue(python_path.is_symlink())
            self.assertEqual(os.readlink(python_path), "Versions/Current/Python")
            self.assertEqual(python_path.read_bytes(), b"python-runtime")

    def test_zip_extraction_rejects_regular_files_nested_inside_archive_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "nested-symlink.zip"
            link = zipfile.ZipInfo("SCAFA_Workforce.app/Contents/Resources/Current")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(link, "Versions/Current")
                zf.writestr(
                    "SCAFA_Workforce.app/Contents/Resources/Current/payload",
                    b"must not be written through a symlink",
                )

            destination = root / "extracted"
            with self.assertRaisesRegex(RuntimeError, "nested inside a symbolic link"):
                updater.safe_extract_zip(archive, destination)
            self.assertFalse(destination.exists())

    def test_macos_copy_failure_restores_previous_application_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = root / "SCAFA_Workforce.app"
            old_executable = installed / "Contents" / "MacOS" / "SCAFA_Workforce"
            old_executable.parent.mkdir(parents=True)
            old_executable.write_text("old application")

            source = root / "package" / "SCAFA_Workforce.app"
            new_executable = source / "Contents" / "MacOS" / "SCAFA_Workforce"
            new_executable.parent.mkdir(parents=True)
            new_executable.write_text("new application")
            archive = root / "update.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.write(new_executable, new_executable.relative_to(source.parent))

            def fail_after_partial_copy(_source, destination, symlinks=True):
                partial = Path(destination)
                partial.mkdir()
                (partial / "partial-install").write_text("incomplete")
                raise OSError("simulated disk-full error")

            with patch.object(updater.shutil, "copytree", side_effect=fail_after_partial_copy):
                with self.assertRaisesRegex(OSError, "simulated disk-full"):
                    updater.apply_macos(archive, installed)

            self.assertEqual(old_executable.read_text(), "old application")
            self.assertFalse((installed / "partial-install").exists())
            self.assertFalse(installed.with_name("SCAFA_Workforce.app.previous").exists())



    def test_update_verification_matches_manifest_and_github_asset_digest(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "update.zip"
            checksum_file = root / "checksums.txt"
            package.write_bytes(b"verified SCAFA update")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            checksum_file.write_text(f"{digest}  {package.name}\n", encoding="utf-8")
            self.assertEqual(
                app.verify_update_asset(package, checksum_file, package.name, f"sha256:{digest}"),
                digest,
            )

    def test_update_verification_rejects_manifest_mismatch_with_github_digest(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "update.zip"
            checksum_file = root / "checksums.txt"
            package.write_bytes(b"verified SCAFA update")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            checksum_file.write_text(f"{'0' * 64}  {package.name}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "manifest does not match GitHub"):
                app.verify_update_asset(package, checksum_file, package.name, f"sha256:{digest}")

    def test_update_verification_rejects_downloaded_package_mismatch(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "update.zip"
            checksum_file = root / "checksums.txt"
            package.write_bytes(b"modified update")
            expected = hashlib.sha256(b"original update").hexdigest()
            checksum_file.write_text(f"{expected}  {package.name}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "failed SHA-256 verification"):
                app.verify_update_asset(package, checksum_file, package.name, f"sha256:{expected}")

    def test_update_verification_rejects_unsupported_published_digest_algorithm(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "update.zip"
            checksum_file = root / "checksums.txt"
            package.write_bytes(b"verified SCAFA update")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            checksum_file.write_text(f"{digest}  {package.name}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "valid SHA-256 digest"):
                app.verify_update_asset(package, checksum_file, package.name, f"sha512:{digest}")

    def test_update_verification_keeps_legacy_manifest_fallback_when_api_digest_is_absent(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "update.zip"
            checksum_file = root / "checksums.txt"
            package.write_bytes(b"legacy release update")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            checksum_file.write_text(f"{digest}  {package.name}\n", encoding="utf-8")
            self.assertEqual(
                app.verify_update_asset(package, checksum_file, package.name),
                digest,
            )


    def test_zip_extraction_rejects_too_many_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "too-many-files.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("one.txt", b"1")
                zf.writestr("two.txt", b"2")
            with patch.object(updater, "MAX_UPDATE_FILES", 1):
                with self.assertRaisesRegex(RuntimeError, "too many files"):
                    updater.safe_extract_zip(archive, root / "extract")

    def test_zip_extraction_rejects_oversized_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "oversized-file.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("large.bin", b"12345")
            with patch.object(updater, "MAX_UPDATE_FILE_BYTES", 4):
                with self.assertRaisesRegex(RuntimeError, "maximum allowed size"):
                    updater.safe_extract_zip(archive, root / "extract")

    def test_zip_extraction_rejects_excessive_total_expanded_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "oversized-archive.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("one.bin", b"123")
                zf.writestr("two.bin", b"456")
            with patch.object(updater, "MAX_UPDATE_TOTAL_BYTES", 5):
                with self.assertRaisesRegex(RuntimeError, "expanded update archive"):
                    updater.safe_extract_zip(archive, root / "extract")


    def test_macos_update_restores_backup_when_previous_swap_left_app_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = root / "SCAFA_Workforce.app"
            backup = root / "SCAFA_Workforce.app.previous"
            old_executable = backup / "Contents" / "MacOS" / "SCAFA_Workforce"
            old_executable.parent.mkdir(parents=True)
            old_executable.write_text("known-good previous application")

            source = root / "package" / "SCAFA_Workforce.app"
            new_executable = source / "Contents" / "MacOS" / "SCAFA_Workforce"
            new_executable.parent.mkdir(parents=True)
            new_executable.write_text("new application")
            archive = root / "update.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.write(new_executable, new_executable.relative_to(source.parent))

            with self.assertRaisesRegex(RuntimeError, "previous application has been restored"):
                updater.apply_macos(archive, installed)

            self.assertEqual(
                (installed / "Contents" / "MacOS" / "SCAFA_Workforce").read_text(),
                "known-good previous application",
            )
            self.assertFalse(backup.exists())

    def test_macos_update_restores_backup_over_partial_bundle_after_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = root / "SCAFA_Workforce.app"
            partial_executable = installed / "Contents" / "MacOS" / "SCAFA_Workforce"
            partial_executable.parent.mkdir(parents=True)
            partial_executable.write_text("incomplete application")
            backup = root / "SCAFA_Workforce.app.previous"
            old_executable = backup / "Contents" / "MacOS" / "SCAFA_Workforce"
            old_executable.parent.mkdir(parents=True)
            old_executable.write_text("known-good previous application")

            source = root / "package" / "SCAFA_Workforce.app"
            new_executable = source / "Contents" / "MacOS" / "SCAFA_Workforce"
            new_executable.parent.mkdir(parents=True)
            new_executable.write_text("new application")
            archive = root / "update.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.write(new_executable, new_executable.relative_to(source.parent))

            with self.assertRaisesRegex(RuntimeError, "previous application has been restored"):
                updater.apply_macos(archive, installed)

            self.assertEqual(
                (installed / "Contents" / "MacOS" / "SCAFA_Workforce").read_text(),
                "known-good previous application",
            )
            self.assertFalse(backup.exists())


    def test_zip_extraction_rejects_oversized_symbolic_link_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "oversized-symlink.zip"
            link = zipfile.ZipInfo("SCAFA_Workforce.app/Contents/Resources/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(link, "x" * (updater.MAX_UPDATE_SYMLINK_BYTES + 1))
            with self.assertRaisesRegex(RuntimeError, "oversized symbolic link"):
                updater.safe_extract_zip(archive, root / "extract")


if __name__=="__main__":
    unittest.main()
