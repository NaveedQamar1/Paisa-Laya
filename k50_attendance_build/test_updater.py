import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import updater


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
            with patch.object(updater.subprocess,"run",return_value=unittest.mock.Mock(returncode=0)) as run, \
                 patch.object(updater.subprocess,"Popen") as launch:
                updater.apply_windows(installer,root)
            run.assert_called_once()
            launch.assert_called_once_with([str(executable)],cwd=str(root))

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


if __name__=="__main__":
    unittest.main()
