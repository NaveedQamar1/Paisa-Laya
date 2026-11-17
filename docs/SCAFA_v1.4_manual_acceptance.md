# SCAFA Workforce v1.4 — manual release acceptance checklist

**Status: NOT YET EXECUTED.** This document is a test procedure, not evidence that clean-machine, installer, database-preservation, or physical-device tests have passed.

Use a disposable test machine and a copy of production data. Never use the only copy of a live attendance database for upgrade or rollback testing.

## 1. Record the test environment

- [ ] Record Windows edition/build or macOS version and CPU architecture.
- [ ] Record installed SCAFA version and installer/package filename.
- [ ] Record the exact Git commit and CI workflow run that produced the package.
- [ ] Record the SHA-256 of the downloaded artifact archive and the installer/package extracted from it.
- [ ] Record whether the machine is a clean install or an upgrade from v1.3.0.
- [ ] Record the Windows/macOS user account used for installation and monitoring.

A successful CI artifact build is not a published release and does not replace these manual gates.

## 2. Windows — clean install, upgrade, and data preservation

### Clean install on Windows 10/11

Use a fresh Windows 10/11 VM or a new standard Windows user profile that has never run SCAFA Workforce or K50 Attendance Manager.

- [ ] Confirm there is no existing SCAFA/K50 application install, no `SCAFAWorkforce` or `K50AttendanceManager` data directory, no SCAFA scheduled task, and no SCAFA monitor process.
- [ ] Record the Windows edition/build and the standard user account; do not use the only copy of production data.
- [ ] Install the v1.4 Windows installer as that standard user and confirm setup does not require administrator elevation.
- [ ] Confirm the application is installed in the expected per-user location and appears in Windows Apps/Installed Apps.
- [ ] Launch the app; verify the displayed version is v1.4.0 and the new database is created at the expected per-user `SCAFAWorkforce/attendance.db` path.
- [ ] Run `PRAGMA integrity_check` against the new database and confirm it returns `ok`; verify the expected tables are initialized.
- [ ] Record the initial monitor/task state. Confirm the app does not silently enable a monitor contrary to the selected/default monitor setting.
- [ ] Create a disposable test employee/profile, close the app, reopen it, and confirm the profile persists.
- [ ] Restart Windows and confirm only the configured SCAFA monitor task starts.
- [ ] Uninstall through Windows Apps/Installed Apps; confirm the application files/task are removed but user data is preserved.
- [ ] Reinstall and confirm the preserved database and test employee are reopened rather than replaced with an empty database.

### Upgrade v1.3.0 to v1.4.0

Use a separate disposable Windows account. Install the latest stable v1.3.0 package first.

### Prepare a recoverable baseline

- [ ] Close SCAFA Workforce and the attendance monitor.
- [ ] Make a verified backup of the user's `SCAFAWorkforce` data directory, including the SQLite database and `device.json` when present.
- [ ] Record the database file size, modification time, and SHA-256.
- [ ] Record representative employee IDs, employee names, attendance rows, leave records, and schedule entries.
- [ ] Open Task Scheduler and record the exact state of `SCAFA Workforce Attendance Monitor`: missing, disabled, ready/not running, or running.
- [ ] If running, confirm the monitor process is visible before starting the upgrade.

### Upgrade v1.3.0 to the v1.4 test installer

- [ ] Run the installer as the same standard Windows user who owns the database and scheduled task.
- [ ] Confirm setup completes without requiring administrator elevation.
- [ ] Confirm the application is installed in the expected per-user location.
- [ ] Confirm the database path is unchanged and the recorded employee, attendance, leave, and schedule data are intact.
- [ ] Confirm the database can be opened and a new test attendance entry can be saved.
- [ ] Confirm the monitor task's post-install state matches its pre-install state: a previously running task is running again; a stopped task remains stopped; a disabled task remains disabled; a missing task is not silently created or enabled.
- [ ] If the monitor was running, confirm the new `scafa-monitor.exe` starts and can fetch a test punch.
- [ ] Confirm no duplicate scheduled task or orphaned monitor process was created.
- [ ] Restart Windows and confirm only the previously enabled ONLOGON task starts.

### Windows updater failure and timeout recovery

These are primarily automated regression cases; use a controlled test environment for manual fault injection.

- [ ] If the stop command times out but a follow-up state probe confirms the task stopped, confirm the updater remembers that it was previously running and restarts it after the installer.
- [ ] If the task remains running after a stop timeout, confirm the installer is not launched.
- [ ] If the follow-up state probe fails or returns an unknown state, confirm the updater fails closed and does not replace application files.
- [ ] If installer execution fails after the monitor stopped, confirm the previous running state is restored.
- [ ] If monitor restart fails, confirm the error explicitly reports that the monitor could not be restarted; do not report a successful update.

### Direct-installer PowerShell timeout and child cleanup

The installer invokes the bundled `scafa-updater.exe` helper for Task Scheduler commands. The helper runs PowerShell with a 45-second `subprocess.run` timeout, captures stdout/stderr, and terminates the PowerShell child if the limit is exceeded. Automated tests cover timeout configuration, partial output, and the helper's exit code; the following host-level behavior still requires manual fault injection.

- [ ] In a disposable Windows VM, use a test-only Task Scheduler command that sleeps longer than 45 seconds; confirm the installer reports a timeout and returns control without waiting indefinitely.
- [ ] Confirm the timed-out PowerShell child process is no longer running and no orphaned child remains.
- [ ] Confirm captured partial stdout/stderr appears in the setup error and setup does not replace application files after an indeterminate task state.
- [ ] If the monitor was running before a stop attempt, confirm setup recovery attempts to restore its prior running state and reports clearly if restoration fails.
- [ ] Repeat the timeout during uninstall cleanup; confirm uninstall aborts before deleting application files and does not claim the scheduled task was removed.


### Windows uninstall

- [ ] Uninstall SCAFA Workforce using Windows Apps/Installed Apps.
- [ ] Confirm the SCAFA-owned scheduled task is removed and no SCAFA monitor process remains.
- [ ] Confirm the user's `SCAFAWorkforce` database, device configuration, and backups are preserved.
- [ ] Confirm no unrelated scheduled tasks or user files are removed.
- [ ] Reinstall and confirm the application can open the preserved database.

## 3. macOS — Intel install, update, and LaunchAgent recovery

Use a disposable Intel Mac and a standard login account.

### Clean install on Intel macOS

- [ ] Use a fresh macOS VM or a new standard user account with no SCAFA app bundle, no `pk.scafa.workforce.monitor.plist`, and no `~/SCAFAWorkforce` data directory.
- [ ] Record macOS version, Intel CPU architecture, user account, and the exact Intel installer artifact ID/workflow run/commit/SHA-256.
- [ ] Install the v1.4 Intel `.pkg` using the release-approved Gatekeeper procedure; record any unsigned-app warning and do not silently bypass a distribution policy.
- [ ] Verify the installed app executable is x86_64, the bundle is in `/Applications`, and the displayed version is v1.4.0.
- [ ] Launch the app and confirm first-run database creation at `~/SCAFAWorkforce/attendance.db`; run `PRAGMA integrity_check` and confirm `ok`.
- [ ] Confirm the bundled monitor and updater helpers exist and are executable.
- [ ] Record the first-run LaunchAgent state and verify it matches the user's monitor setting; do not assume that a missing/disabled agent should be enabled.
- [ ] Restart/log out and back in; verify the app opens the same database and only the configured LaunchAgent starts.

### Upgrade from v1.3.0

- [ ] Record the macOS version, Intel architecture, installed SCAFA version, and package SHA-256.
- [ ] Back up `~/SCAFAWorkforce` and record the database checksum and representative records.
- [ ] Record whether `~/Library/LaunchAgents/pk.scafa.workforce.monitor.plist` exists and whether the LaunchAgent is loaded in the original user's GUI domain.
- [ ] Upgrade from v1.3.0 using the v1.4 Intel package.
- [ ] Confirm the app bundle is replaced without deleting the user's database or device configuration.
- [ ] Confirm a previously loaded LaunchAgent is stopped before bundle replacement and restored only if it was loaded before the update.
- [ ] Confirm a previously unloaded/missing agent is not silently loaded or recreated.
- [ ] Confirm a failed `launchctl bootout` proceeds only when a subsequent state probe positively confirms the agent is unloaded.
- [ ] Confirm an indeterminate or still-loaded state aborts the update before replacing the app bundle.
- [ ] Confirm rollback restores the previous app bundle and its previous monitor state.
- [ ] Confirm a stale `.previous` backup cannot downgrade a successfully updated app on the next run.
- [ ] Launch the updated app and verify the displayed version and device connection.
- [ ] Reboot/log out and back in; verify only the previously enabled LaunchAgent starts.
- [ ] Uninstall the app and confirm user data is preserved.

### Intel icon patch

- [ ] Install the icon patch on an existing unsigned SCAFA app bundle.
- [ ] Confirm the app executable, database, and other bundle files are unchanged; only the icon resource and icon plist key change.
- [ ] Confirm a code-signed app is rejected without modification.
- [ ] Confirm an absent app bundle or missing patch resource produces a clear error and no partial modification.
- [ ] Confirm the package does not stage or rename the whole app bundle to `.previous`.


### Apple Silicon — arm64 app ZIP smoke test

The current PR build produces an Apple Silicon application ZIP, not a signed `.pkg` installer. Use a disposable Apple Silicon Mac (M-series) and a standard login account.

- [ ] Record macOS version, Mac model/chip, exact artifact ID, workflow run, commit SHA, and archive SHA-256.
- [ ] Extract the Apple Silicon ZIP and verify the main executable reports `arm64` (for example, with `file` or `lipo -archs`); do not rely only on the runner label or ZIP name.
- [ ] Copy the app bundle to `/Applications`, launch it, and confirm macOS does not report an architecture or missing-library error.
- [ ] Confirm the displayed application version is v1.4.0 and the application opens the expected `~/SCAFAWorkforce` database rather than creating an empty parallel data directory.
- [ ] Confirm the bundled monitor and updater helpers exist, are executable, and can be launched by their intended application workflows.
- [ ] Verify first-run monitor/LaunchAgent setup, normal stop/start, logout/login recovery, and that an intentionally disabled or absent monitor is not silently enabled.
- [ ] Perform a test update check and verify the updater's checksum validation and rollback behavior without using live production data.
- [ ] Confirm employee, attendance, device configuration, and backup data remain intact after app replacement and restart.
- [ ] Record logs/screenshots and the result for each check; mark unavailable physical-device checks as not run rather than passed.


## 4. Attendance device and synchronization

Perform these tests against an available physical K50 device; CI cannot substitute for them.

- [ ] Discover/connect to the device using the expected IP, port, and communication key.
- [ ] Fetch attendance records for a known date range and compare representative rows with the device.
- [ ] Sync the same range twice and confirm the second sync creates no duplicate punches.
- [ ] Test an employee with multiple punches on the same day.
- [ ] Test overnight shifts and punches around midnight.
- [ ] Test an employee with no punches and a device with an empty response.
- [ ] Disconnect the network during fetch/sync and confirm the UI reports failure without marking incomplete data as synced.
- [ ] Reconnect and retry; confirm no data loss or duplicate attendance.
- [ ] Confirm employee identifiers, timestamps, and timezone interpretation remain consistent.

## 5. Employee, dashboard, and reporting regression

- [ ] Create, edit, deactivate, and view an employee profile.
- [ ] Confirm employee history and linked attendance remain associated with the correct employee after edits.
- [ ] Test duplicate employee identifiers and invalid required fields.
- [ ] Verify dashboard totals against the underlying attendance records for a known date range.
- [ ] Export Excel and confirm employee names/statuses beginning with `=`, `+`, `-`, or `@` remain literal text rather than formulas.
- [ ] Export PDF and confirm long names, IDs, and status values render safely and legibly.
- [ ] Verify CSV/PDF/Excel exports against the same known records.
- [ ] Confirm backup and restore preserve employees, attendance, schedules, leave, and settings.
- [ ] Test backup restore while the background monitor is enabled; confirm maintenance locking prevents partial or inconsistent writes.

## 6. Evidence and sign-off

For each manual test, record the result, date, operator, machine, exact commit, workflow run, artifact ID, and any log/screenshot reference.

### Latest exact-head automated CI evidence — implementation commit \`94704ac8309f3038c3c47f6e6d416684d7f63605\`, regression-test head \`1f86e32e468268569f09bd16f6c731370073347a\`

- Validation run [#44073752501](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44073752501), exact PR head SHA \`1f86e32\`:
  - Windows: **200 tests total, 198 passed, 2 skipped** (POSIX-only process-group test and hosted-runner symbolic-link restriction). The Windows PowerShell descendant-process termination integration test passed.
  - Intel macOS: **200 tests total, 198 passed, 2 skipped** (Windows-only ScheduledTasks and Windows process-tree integration tests). The POSIX descendant-process cleanup test passed.
  - Apple Silicon: **200 tests total, 198 passed, 2 skipped** (the same two Windows-only tests). The POSIX descendant-process cleanup test passed.
- Packaging run [#44073752386](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44073752386), same exact PR head SHA: Windows installer, Intel macOS app ZIP, Intel installer, Intel icon patch, and Apple Silicon app ZIP all built and uploaded. All build and upload steps succeeded; the publish job was skipped as expected for a pull request.
- The five verified CI artifacts below were created on 17 November 2026 and expire **15 February 2027 11:24:35 UTC**. SHA-256 values are GitHub's artifact archive digests.

| Artifact | Download | Size | Created (UTC) | Expires (UTC) | Archive SHA-256 |
|---|---|---:|---|---|---|
| Windows installer \`release-windows\` | [#14324570268](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44073752386/artifacts/14324570268) | 48,462,899 B | 11:27:09 | 15 Feb 2027 11:24:35 | \`ff376772228a942f0485b87c1302ae5c2f6b8a63bc7b427b3a3d4d72f124a952\` |
| Apple Silicon app ZIP \`release-macos-apple-silicon\` | [#14323937471](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44073752386/artifacts/14323937471) | 37,154,483 B | 11:25:47 | 15 Feb 2027 11:24:35 | \`b3ff6126bc7080289655910d711c7aa020849ba3b749b904fd328fa61d3d38ae\` |
| Intel macOS app ZIP \`release-macos-intel\` | [#14323797231](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44073752386/artifacts/14323797231) | 39,842,821 B | 11:28:07 | 15 Feb 2027 11:24:35 | \`729f89ae8b50bcccaadf6cadc2e3bdf41510e8f52ffc4897df0611742e0aceba\` |
| Intel macOS installer \`release-macos-intel-installer\` | [#14323274735](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44073752386/artifacts/14323274735) | 39,823,617 B | 11:28:11 | 15 Feb 2027 11:24:35 | \`48dc70d7e90bf57c93e716ea999b15e218346af1736b1ccdbfcf62fa0bb8717b\` |
| Intel icon patch \`release-macos-intel-icon-patch\` | [#14323204797](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44073752386/artifacts/14323204797) | 92,954 B | 11:28:12 | 15 Feb 2027 11:24:35 | \`ac71c98c8b3f77e1369faca42e9a3eeec311ff167cca3921926562b342c8485e\` |

These are temporary CI artifacts, not published release assets. The Apple Silicon deliverable is an app ZIP, not a \`.pkg\` installer. Exact-head CI confirms automated tests, compilation, and packaging; it does not prove real-machine installation, data preservation, signing, notarization, or physical-device operation.

The implementation commit \`94704ac8309f3038c3c47f6e6d416684d7f63605\` now terminates the installer PowerShell process tree on timeout: Windows uses \`taskkill /T /F\`, while POSIX test runners terminate the isolated process group. The helper waits for termination and retains captured output. Regression tests in \`1f86e32e468268569f09bd16f6c731370073347a\` verify descendant cleanup and partial-output preservation. The evidence above validates these changes on exact PR head \`1f86e32\`.

| Gate | Result | Evidence |
|---|---|---|
| Windows clean install | Not run | Disposable Windows 10/11 VM required |
| Windows v1.3.0 → v1.4 upgrade | Not run | Disposable Windows 10/11 VM required |
| Windows monitor state preservation | Automated regression tests passed on \`1f86e32\`; manual not run | Exact-head validation #44073752501 |
| Windows missing scheduled-task detection | Windows PowerShell integration test passed on \`1f86e32\`; full installer scenario not run | Exact-head validation #44073752501 |
| Windows updater timeout/rollback | Automated regression tests passed on \`1f86e32\`; manual fault injection not run | Exact-head validation #44073752501 |
| Windows direct-installer PowerShell timeout/termination | Automated regression tests passed on \`1f86e32\`; manual fault injection not run | Exact-head validation #44073752501 |
| Windows PowerShell descendant-process cleanup | Windows integration test passed on \`1f86e32\`; manual installer fault injection not run | Exact-head validation #44073752501 |
| Windows uninstall/data preservation | Not run | Disposable Windows 10/11 VM required |
| Intel macOS clean install | Not run | Physical Mac or disposable VM required |
| Intel macOS v1.3.0 → v1.4 upgrade | Not run | Physical Mac or disposable VM required |
| macOS LaunchAgent stop/restart/rollback | Not run | Physical Mac or disposable VM required |
| Intel icon patch | Not run | Physical Intel Mac required |
| Apple Silicon app ZIP launch/helpers/data preservation | Not run | Physical Apple Silicon Mac required |
| Physical K50 discovery/fetch/sync | Not run | Physical K50 device and network required |
| Employee/dashboard/Excel/PDF regression | Automated suite passed; end-to-end GUI checks not run | Exact-head validation #44073752501 |
| Backup/restore with monitor enabled | Automated regression tests passed; live monitor/restore acceptance not run | Exact-head validation #44073752501 |

## 7. Distribution signing and notarization decision

The current CI workflow builds Windows and macOS artifacts but does not include Windows Authenticode signing or Apple Developer ID signing/notarization steps. Successful compilation and artifact upload do not establish publisher identity or Gatekeeper/SmartScreen acceptance.

- [ ] Release owner decides whether signed Windows distribution is required for v1.4.0.
- [ ] Release owner decides whether Developer ID signing and Apple notarization are required for Intel and Apple Silicon distribution.
- [ ] If signing is required, configure credentials only as protected GitHub Actions secrets; never commit certificates, private keys, passwords, or notarization credentials.
- [ ] Add platform-specific signing/notarization steps and verify the final distributed binaries/packages (not only intermediate build outputs).
- [ ] Record certificate identity, notarization result/ticket where applicable, and final installer/package checksums.
- [ ] If signing is intentionally deferred, document the accepted unsigned-distribution warning and the supported installation instructions before publication.


**Release gate:** do not describe v1.4 as production-ready until the applicable CI jobs pass, Windows and Intel macOS artifacts are verified, database-preservation checks pass, and the physical-device/manual acceptance rows above are signed off. A skipped or unavailable platform job remains an open gate.
