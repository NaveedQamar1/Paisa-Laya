import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import updater


class UpdaterHelperTests(unittest.TestCase):
    def test_wait_for_already_exited_process_returns(self):
        updater.wait_for_process(99999999, timeout=0.1)

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
            with patch.object(updater.subprocess,"Popen") as launch:
                updater.apply_macos(archive,installed)
            self.assertEqual((installed/"Contents"/"MacOS"/"SCAFA_Workforce").read_text(),"new")
            launch.assert_called_once()


if __name__=="__main__":
    unittest.main()
