"""Regression checks for the Intel macOS component-package lifecycle scripts."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
INSTALLER = ROOT / "installer"
PREINSTALL = INSTALLER / "macos-app-scripts" / "preinstall"
POSTINSTALL = INSTALLER / "macos-app-scripts" / "postinstall"
WORKFLOW = (
    ROOT.parent
    / ".github"
    / "workflows"
    / "scafa-release.yml"
)


class MacOSPackageLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preinstall = PREINSTALL.read_text(encoding="utf-8")
        cls.postinstall = POSTINSTALL.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_preinstall_refuses_to_replace_an_open_gui_application(self):
        self.assertIn("pgrep -f", self.preinstall)
        self.assertIn("Quit SCAFA Workforce before installing or upgrading", self.preinstall)
        self.assertIn("exit 1", self.preinstall)

    def test_preinstall_checks_all_users_and_fails_closed_on_ambiguous_launchd_state(self):
        self.assertIn("dscl . -list /Users UniqueID", self.preinstall)
        self.assertIn('launchctl print "$service"', self.preinstall)
        self.assertIn("Could not determine whether monitor", self.preinstall)
        self.assertIn("More than one SCAFA Workforce monitor is loaded", self.preinstall)

    def test_preinstall_validates_launchagent_identity_and_ownership_before_bootout(self):
        for required in (
            '[ -L "$plist" ]',
            'stat -f \'%u\' "$plist"',
            "PlistBuddy -c 'Print :Label'",
            "PlistBuddy -c 'Print :ProgramArguments:0'",
            'launchctl bootout "$service"',
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.preinstall)
        self.assertLess(
            self.preinstall.index('stat -f \'%u\' "$plist"'),
            self.preinstall.index('launchctl bootout "$service"'),
        )

    def test_preinstall_persists_protected_recovery_state_before_stopping_monitor(self):
        self.assertIn(
            'STATE_FILE="/var/db/scafa-workforce-installer/monitor-state"',
            self.preinstall,
        )
        self.assertIn('/usr/bin/install -d -o root -g wheel -m 700 "$STATE_DIR"', self.preinstall)
        self.assertIn('/bin/chmod 600 "$tmp_file"', self.preinstall)
        self.assertLess(
            self.preinstall.index('/bin/mv "$tmp_file" "$STATE_FILE"'),
            self.preinstall.index('launchctl bootout "$service"'),
        )

    def test_postinstall_restores_only_a_previously_loaded_monitor(self):
        self.assertIn('if [ ! -e "$STATE_FILE" ] && [ ! -L "$STATE_FILE" ]; then', self.postinstall)
        self.assertIn('No previously loaded monitor was recorded', self.postinstall)
        self.assertIn('launchctl bootstrap "$domain" "$plist"', self.postinstall)
        self.assertIn('RunAtLoad', self.postinstall)

    def test_postinstall_confirms_monitor_before_removing_recovery_state(self):
        bootstrap = self.postinstall.index('launchctl bootstrap "$domain" "$plist"')
        confirmation = self.postinstall.index('launchctl print "$service"', bootstrap)
        cleanup = self.postinstall.index('clear_state\\nlog "Restored and verified the previously loaded monitor', confirmation)
        self.assertIn('/bin/rm -f "$STATE_FILE"', self.postinstall)
        self.assertLess(bootstrap, confirmation)
        self.assertLess(confirmation, cleanup)
        self.assertIn("The monitor bootstrap completed, but launchd did not confirm", self.postinstall)

    def test_release_workflow_builds_and_inspects_the_scripted_component_package(self):
        self.assertIn(
            'pkgbuild --component dist/SCAFA_Workforce.app --install-location /Applications --scripts "$MACOS_INSTALLER_SCRIPTS"',
            self.workflow,
        )
        self.assertIn('/bin/bash -n "$MACOS_INSTALLER_SCRIPTS/preinstall"', self.workflow)
        self.assertIn('/bin/bash -n "$MACOS_INSTALLER_SCRIPTS/postinstall"', self.workflow)
        self.assertIn('Scripts/preinstall', self.workflow)
        self.assertIn('Scripts/postinstall', self.workflow)
        self.assertIn('test -x "$PACKAGE_CHECK_DIR/app-installer/Scripts/preinstall"', self.workflow)
        self.assertIn('test -x "$PACKAGE_CHECK_DIR/app-installer/Scripts/postinstall"', self.workflow)


if __name__ == "__main__":
    unittest.main()
