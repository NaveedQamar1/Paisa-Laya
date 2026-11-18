import os
import subprocess
import unittest
from pathlib import Path


class WindowsInstallerMonitorLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (
            Path(__file__).parent
            / "installer"
            / "SCAFA_Workforce.iss"
        ).read_text(encoding="utf-8")
        cls.code = cls.script.split("[Code]", 1)[1]

    def test_install_inspects_monitor_before_replacing_files(self):
        prepare = self.code.split(
            "function PrepareToInstall", 1
        )[1].split("procedure CurStepChanged", 1)[0]
        self.assertIn("ReadMonitorTaskState(State, ErrorText)", prepare)
        self.assertIn("CompareText(State, 'Running') = 0", prepare)
        self.assertIn("StopMonitorTask(Outcome, ErrorText)", prepare)
        self.assertIn("Installation was stopped before replacing files", prepare)

    def test_stop_command_rechecks_running_state_before_stopping(self):
        stop = self.code.split(
            "function StopMonitorTask", 1
        )[1].split("function StartMonitorTask", 1)[0]
        self.assertIn("if ($task.State -ne ''Running'')", stop)
        self.assertIn("Stop-ScheduledTask", stop)
        self.assertLess(
            stop.index("if ($task.State -ne ''Running'')"),
            stop.index("Stop-ScheduledTask"),
        )
        self.assertIn("AddSeconds(15)", stop)
        self.assertIn("Milliseconds 250", stop)

    def test_originally_running_monitor_is_restored_on_success_or_abort(self):
        self.assertIn("if CurStep = ssDone then", self.code)
        self.assertIn("SetupSucceeded := True", self.code)
        self.assertIn(
            "if MonitorWasRunning and not MonitorRestored then",
            self.code,
        )
        self.assertIn("RestoreMonitorTask(ErrorText)", self.code)
        self.assertIn("Start-ScheduledTask", self.code)

    def test_uninstall_removes_only_the_root_scafa_task_and_fails_closed(self):
        self.assertIn(
            "Unregister-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92)",
            self.code,
        )
        self.assertIn("if CurUninstallStep = usUninstall then", self.code)
        self.assertIn("if not RemoveMonitorTask(ErrorText) then", self.code)
        self.assertIn("Abort;", self.code)
        self.assertIn("Monitor task is still active", self.code)

    def test_missing_task_is_tolerated_but_other_query_errors_fail(self):
        read_state = self.code.split(
            "function ReadMonitorTaskState", 1
        )[1].split("function StopMonitorTask", 1)[0]
        remove_task = self.code.split(
            "function RemoveMonitorTask", 1
        )[1].split("function PrepareToInstall", 1)[0]
        for error_id in (
            "CmdletizationQuery_NotFound",
            "NoMatchingCimInstance",
            "NoMatchingTasksFound",
        ):
            self.assertIn(error_id, read_state)
            self.assertIn(error_id, remove_task)
        self.assertIn("exit 2", self.code)
        self.assertIn("CompareText(OutputText, 'Missing') = 0", self.code)

    @unittest.skipUnless(os.name == "nt", "ScheduledTasks is available only on Windows")
    def test_windows_missing_task_error_identifier_is_supported(self):
        script = r"""
$ErrorActionPreference = 'Stop'
Import-Module ScheduledTasks -ErrorAction Stop
$taskName = 'SCAFA-Workforce-Definitely-Missing-For-CI-Regression-00000000'
try {
    Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop | Out-Null
    Write-Output 'FOUND'
    exit 10
} catch {
    Write-Output ([string]$_.FullyQualifiedErrorId)
    exit 0
}
"""
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        error_id = result.stdout.strip()
        self.assertNotEqual(error_id, "FOUND")
        self.assertTrue(
            error_id.startswith(
                (
                    "CmdletizationQuery_NotFound",
                    "NoMatchingCimInstance",
                    "NoMatchingTasksFound",
                )
            ),
            error_id,
        )

    def test_installer_uses_bounded_updater_helper_for_task_scheduler_commands(self):
        self.assertIn(
            r'Source: "..\..\dist\scafa-updater.exe"; Flags: dontcopy',
            self.script,
        )
        prepare = self.code.split(
            "function PrepareToInstall", 1
        )[1].split("procedure CurStepChanged", 1)[0]
        self.assertIn("ExtractTemporaryFile('scafa-updater.exe')", prepare)
        self.assertLess(
            prepare.index("ExtractTemporaryFile('scafa-updater.exe')"),
            prepare.index("ReadMonitorTaskState(State, ErrorText)"),
        )

        runner = self.code.split(
            "function RunMonitorPowerShell", 1
        )[1].split("function ReadMonitorTaskState", 1)[0]
        self.assertIn("ExecAndCaptureOutput(", runner)
        self.assertIn("MonitorHelperPath,", runner)
        self.assertIn("--installer-powershell-script", runner)
        self.assertNotIn("WindowsPowerShell", runner)

        uninstall = self.code.split(
            "procedure CurUninstallStepChanged", 1
        )[1]
        self.assertIn(
            r"MonitorHelperPath := ExpandConstant('{app}\scafa-updater.exe')",
            uninstall,
        )
        self.assertIn("if not FileExists(MonitorHelperPath) then", uninstall)

    def test_installer_lifecycle_does_not_delete_user_attendance_data(self):
        self.assertNotIn("SCAFAWorkforce", self.code)
        self.assertNotIn("DelTree", self.code)
        self.assertNotIn("DeleteFile", self.code)


    def test_pascal_line_break_tokens_never_start_preprocessor_directives(self):
        for line_number, line in enumerate(self.code.splitlines(), start=1):
            self.assertFalse(
                line.lstrip().startswith("#"),
                f"Pascal line-break token starts an Inno Setup preprocessor directive at [Code] line {line_number}.",
            )


if __name__ == "__main__":
    unittest.main()
