"""Regression checks for the Intel macOS component-package lifecycle scripts."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
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
        self.assertIn('STATE_DIR="/var/db/scafa-workforce-installer"', self.preinstall)
        self.assertIn('STATE_FILE="$STATE_DIR/monitor-state"', self.preinstall)
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
        restored_log = self.postinstall.index(
            'log "Restored and verified the previously loaded monitor',
            confirmation,
        )
        cleanup = self.postinstall.rfind("clear_state", confirmation, restored_log)
        self.assertIn('/bin/rm -f "$STATE_FILE"', self.postinstall)
        self.assertLess(bootstrap, confirmation)
        self.assertGreaterEqual(cleanup, confirmation)
        self.assertLess(cleanup, restored_log)
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



@unittest.skipUnless(
    sys.platform == "darwin" and shutil.which("bash"),
    "Lifecycle command simulation runs on the macOS CI host.",
)
class MacOSInstallerScriptExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.plist = self.home / "Library" / "LaunchAgents" / "pk.scafa.workforce.monitor.plist"
        self.plist.parent.mkdir(parents=True)
        self.plist.write_text("simulated LaunchAgent", encoding="utf-8")

        self.app_bundle = self.root / "Applications" / "SCAFA_Workforce.app"
        executable_dir = self.app_bundle / "Contents" / "MacOS"
        executable_dir.mkdir(parents=True)
        (executable_dir / "SCAFA_Workforce").write_text("app", encoding="utf-8")
        (executable_dir / "scafa-monitor").write_text("monitor", encoding="utf-8")
        (executable_dir / "scafa-monitor").chmod(0o755)

        self.state_dir = self.root / "installer-state"
        self.state_file = self.state_dir / "monitor-state"
        self.launch_state = self.root / "launch-state"
        self.call_log = self.root / "launchctl-calls.log"
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir()
        self._write_fake_commands()

        self.base_env = os.environ.copy()
        self.base_env.update({
            "SCAFA_TEST_HOME": str(self.home),
            "SCAFA_TEST_APP_BUNDLE": str(self.app_bundle),
            "SCAFA_TEST_LAUNCH_STATE": str(self.launch_state),
            "SCAFA_TEST_CALL_LOG": str(self.call_log),
            "SCAFA_TEST_GUI_RUNNING": "0",
            "SCAFA_TEST_NO_GUI_DOMAIN": "0",
            "SCAFA_TEST_BOOTOUT_FAIL": "0",
            "SCAFA_TEST_BOOTOUT_STATE": "loaded",
            "SCAFA_TEST_BOOTSTRAP_FAIL": "0",
        })
        self.bash = shutil.which("bash")

    def tearDown(self):
        self.temp.cleanup()

    def _write_command(self, name, body):
        path = self.fake_bin / name
        path.write_text("#!/bin/bash\nset -e\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def _write_fake_commands(self):
        self._write_command("id", 'echo 0\n')
        self._write_command(
            "pgrep",
            'if [ "${SCAFA_TEST_GUI_RUNNING:-0}" = "1" ]; then exit 0; fi\nexit 1\n',
        )
        self._write_command(
            "dscl",
            'if [ "$2" = "-list" ]; then echo "scafa 501"; exit 0; fi\n'
            'if [ "$2" = "-read" ]; then echo "NFSHomeDirectory: $SCAFA_TEST_HOME"; exit 0; fi\n'
            'echo "unexpected dscl call: $*" >&2; exit 2\n',
        )
        self._write_command(
            "stat",
            'case "$2" in\n'
            '  %u) case "$3" in "$SCAFA_TEST_HOME"/*) echo 501;; *) echo 0;; esac ;;\n'
            '  %Lp) echo 600 ;;\n'
            '  *) exit 2 ;;\n'
            'esac\n',
        )
        self._write_command(
            "PlistBuddy",
            'case "$2" in\n'
            '  "Print :Label") echo "pk.scafa.workforce.monitor" ;;\n'
            '  "Print :ProgramArguments:0") echo "$SCAFA_TEST_APP_BUNDLE/Contents/MacOS/scafa-monitor" ;;\n'
            '  "Print :RunAtLoad") echo "true" ;;\n'
            '  *) echo "unexpected plist query: $2" >&2; exit 2 ;;\n'
            'esac\n',
        )
        self._write_command(
            "install",
            'mkdir -p "$8"\nchmod 700 "$8"\n',
        )
        self._write_command("chown", 'exit 0\n')
        self._write_command(
            "launchctl",
            'printf "%s\\n" "$*" >> "$SCAFA_TEST_CALL_LOG"\n'
            'case "$1" in\n'
            '  print)\n'
            '    if [ "$2" = "gui/501" ]; then\n'
            '      if [ "${SCAFA_TEST_NO_GUI_DOMAIN:-0}" = "1" ]; then echo "Could not find domain specified." >&2; exit 113; fi\n'
            '      exit 0\n'
            '    fi\n'
            '    if [ "$2" = "gui/501/pk.scafa.workforce.monitor" ]; then\n'
            '      state=$(cat "$SCAFA_TEST_LAUNCH_STATE")\n'
            '      case "$state" in\n'
            '        loaded) exit 0 ;;\n'
            '        unknown) echo "Operation not permitted" >&2; exit 1 ;;\n'
            '        *) echo \'Could not find service "pk.scafa.workforce.monitor"\' >&2; exit 113 ;;\n'
            '      esac\n'
            '    fi\n'
            '    echo "unexpected launchctl print target: $2" >&2; exit 2 ;;\n'
            '  bootout)\n'
            '    if [ "${SCAFA_TEST_BOOTOUT_FAIL:-0}" = "1" ]; then\n'
            '      if [ "${SCAFA_TEST_BOOTOUT_STATE:-loaded}" = "unloaded" ]; then echo unloaded > "$SCAFA_TEST_LAUNCH_STATE"; elif [ "${SCAFA_TEST_BOOTOUT_STATE:-loaded}" = "unknown" ]; then echo unknown > "$SCAFA_TEST_LAUNCH_STATE"; fi\n'
            '      echo "simulated bootout failure" >&2; exit 1\n'
            '    fi\n'
            '    echo unloaded > "$SCAFA_TEST_LAUNCH_STATE"; exit 0 ;;\n'
            '  bootstrap)\n'
            '    if [ "${SCAFA_TEST_BOOTSTRAP_FAIL:-0}" = "1" ]; then echo "simulated bootstrap failure" >&2; exit 1; fi\n'
            '    echo loaded > "$SCAFA_TEST_LAUNCH_STATE"; exit 0 ;;\n'
            'esac\n'
            'echo "unexpected launchctl command: $*" >&2; exit 2\n',
        )

    def _script_copy(self, source, name):
        script = source.read_text(encoding="utf-8")
        command_map = {
            "/usr/bin/id": "id",
            "/usr/bin/pgrep": "pgrep",
            "/usr/bin/dscl": "dscl",
            "/bin/launchctl": "launchctl",
            "/usr/bin/stat": "stat",
            "/usr/libexec/PlistBuddy": "PlistBuddy",
            "/usr/bin/install": "install",
            "/usr/sbin/chown": "chown",
        }
        for original, command in command_map.items():
            script = script.replace(
                original,
                shlex.quote(str(self.fake_bin / command)),
            )
        script = script.replace(
            'APP_BUNDLE="/Applications/SCAFA_Workforce.app"',
            f'APP_BUNDLE="{self.app_bundle}"',
        )
        script = script.replace(
            'STATE_DIR="/var/db/scafa-workforce-installer"',
            f'STATE_DIR="{self.state_dir}"',
        )
        destination = self.root / name
        destination.write_text(script, encoding="utf-8")
        destination.chmod(0o755)
        return destination

    def _run(self, source, name, **extra_env):
        script = self._script_copy(source, name)
        env = self.base_env.copy()
        env.update(extra_env)
        return subprocess.run(
            [self.bash, str(script)],
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
            check=False,
        )

    def _prepare_loaded_state(self, state="loaded"):
        self.launch_state.write_text(state, encoding="ascii")

    def _prepare_recovery_marker(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text("501\n", encoding="ascii")
        self.state_file.chmod(0o600)

    def _calls(self):
        if not self.call_log.exists():
            return []
        return self.call_log.read_text(encoding="utf-8").splitlines()

    def test_preinstall_stops_loaded_monitor_and_records_recovery_state(self):
        self._prepare_loaded_state("loaded")
        result = self._run(PREINSTALL, "preinstall")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "501")
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "unloaded")
        self.assertIn("bootout gui/501/pk.scafa.workforce.monitor", self._calls())

    def test_preinstall_preserves_an_unloaded_monitor(self):
        self._prepare_loaded_state("unloaded")
        result = self._run(PREINSTALL, "preinstall")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse(self.state_file.exists())
        self.assertFalse(any(call.startswith("bootout ") for call in self._calls()))

    def test_preinstall_aborts_on_ambiguous_launchd_state_before_stopping(self):
        self._prepare_loaded_state("unknown")
        result = self._run(PREINSTALL, "preinstall")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.state_file.exists())
        self.assertFalse(any(call.startswith("bootout ") for call in self._calls()))

    def test_preinstall_aborts_if_gui_application_is_open(self):
        self._prepare_loaded_state("loaded")
        result = self._run(PREINSTALL, "preinstall", SCAFA_TEST_GUI_RUNNING="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.state_file.exists())
        self.assertEqual(self._calls(), [])

    def test_preinstall_accepts_nonzero_bootout_when_monitor_is_confirmed_unloaded(self):
        self._prepare_loaded_state("loaded")
        result = self._run(
            PREINSTALL,
            "preinstall",
            SCAFA_TEST_BOOTOUT_FAIL="1",
            SCAFA_TEST_BOOTOUT_STATE="unloaded",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "unloaded")
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "501")

    def test_preinstall_retains_recovery_marker_when_bootout_state_is_indeterminate(self):
        self._prepare_loaded_state("loaded")
        result = self._run(
            PREINSTALL,
            "preinstall",
            SCAFA_TEST_BOOTOUT_FAIL="1",
            SCAFA_TEST_BOOTOUT_STATE="unknown",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state_file.exists())
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "unknown")

    def test_preinstall_aborts_when_bootout_fails_and_monitor_remains_loaded(self):
        self._prepare_loaded_state("loaded")
        result = self._run(
            PREINSTALL,
            "preinstall",
            SCAFA_TEST_BOOTOUT_FAIL="1",
            SCAFA_TEST_BOOTOUT_STATE="loaded",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.state_file.exists())
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "loaded")

    def test_postinstall_restores_and_confirms_previously_loaded_monitor(self):
        self._prepare_loaded_state("unloaded")
        self._prepare_recovery_marker()
        result = self._run(POSTINSTALL, "postinstall")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "loaded")
        self.assertFalse(self.state_file.exists())
        self.assertTrue(any(call.startswith("bootstrap gui/501 ") for call in self._calls()))
        self.assertIn("print gui/501/pk.scafa.workforce.monitor", self._calls())

    def test_postinstall_leaves_previously_disabled_monitor_unloaded(self):
        self._prepare_loaded_state("unloaded")
        result = self._run(POSTINSTALL, "postinstall")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse(any(call.startswith("bootstrap ") for call in self._calls()))
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "unloaded")

    def test_postinstall_defers_to_login_when_gui_domain_is_absent(self):
        self._prepare_loaded_state("unloaded")
        self._prepare_recovery_marker()
        result = self._run(
            POSTINSTALL,
            "postinstall",
            SCAFA_TEST_NO_GUI_DOMAIN="1",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse(self.state_file.exists())
        self.assertFalse(any(call.startswith("bootstrap ") for call in self._calls()))

    def test_postinstall_retains_recovery_marker_when_new_monitor_helper_is_missing(self):
        self._prepare_loaded_state("unloaded")
        self._prepare_recovery_marker()
        (self.app_bundle / "Contents" / "MacOS" / "scafa-monitor").unlink()
        result = self._run(POSTINSTALL, "postinstall")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state_file.exists())
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "unloaded")

    def test_postinstall_retains_recovery_marker_when_monitor_restore_fails(self):
        self._prepare_loaded_state("unloaded")
        self._prepare_recovery_marker()
        result = self._run(
            POSTINSTALL,
            "postinstall",
            SCAFA_TEST_BOOTSTRAP_FAIL="1",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state_file.exists())
        self.assertEqual(self.launch_state.read_text(encoding="ascii").strip(), "unloaded")


if __name__ == "__main__":
    unittest.main()
