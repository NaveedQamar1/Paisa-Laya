# SCAFA Workforce v1.4 — manual release acceptance checklist

**Status: NOT YET EXECUTED.** This document is a test procedure, not evidence that clean-machine, installer, database-preservation, or physical-device tests have passed.

Use a disposable test machine and a copy of production data. Never use the only copy of a live attendance database for upgrade or rollback testing.
## Language scope

SCAFA Workforce v1.4 is an English-only application. Interface labels, prompts, validation messages, and report headings are expected in English. The release-acceptance dataset uses Latin-script employee names and English status text. Urdu/Arabic font embedding, right-to-left layout, and script shaping are explicitly out of scope and are not release blockers. Continue testing PDF/CSV/Excel escaping, wrapping, and legibility for ordinary English text and long employee names/identifiers.

## Initial delivery scope

- Required targets are **Windows x64 and Intel macOS (x86_64) only**. Apple Silicon/ARM64 builds, CI jobs, artifacts, and physical tests are outside the initial v1.4 delivery scope. An omitted or cancelled ARM64 job is not a release blocker.
- The physical K50 test in section 4 is **post-delivery user acceptance**, not a blocker to producing the initial tester packages. CI must still pass its mock/fixture coverage for discovery handshakes, fetch, duplicate-safe sync, malformed rows, and connection cleanup/recovery.


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

The installer invokes the bundled `scafa-updater.exe` helper for Task Scheduler commands. The helper starts PowerShell with a bounded 45-second process wait, captures stdout/stderr, attempts process-tree termination and reaping when the limit is exceeded, and fails closed if cleanup cannot be confirmed. Automated tests cover timeout configuration, partial output, descendant cleanup, and the unreaped-process failure path; the following host-level behavior still requires manual fault injection.

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


### Future-only architecture checklist — Apple Silicon (outside initial v1.4 scope)

The initial v1.4 workflow is limited to Windows x64 and Intel macOS. It is not expected to produce an Apple Silicon artifact, and no M-series hardware test is required for this delivery. The following checklist is retained only as optional future architecture-expansion guidance; do not count it as an initial v1.4 acceptance gate.

- [ ] Record macOS version, Mac model/chip, exact artifact ID, workflow run, commit SHA, and archive SHA-256.
- [ ] Extract the Apple Silicon ZIP and verify the main executable reports `arm64` (for example, with `file` or `lipo -archs`); do not rely only on the runner label or ZIP name.
- [ ] Copy the app bundle to `/Applications`, launch it, and confirm macOS does not report an architecture or missing-library error.
- [ ] Confirm the displayed application version is v1.4.0 and the application opens the expected `~/SCAFAWorkforce` database rather than creating an empty parallel data directory.
- [ ] Confirm the bundled monitor and updater helpers exist, are executable, and can be launched by their intended application workflows.
- [ ] Verify first-run monitor/LaunchAgent setup, normal stop/start, logout/login recovery, and that an intentionally disabled or absent monitor is not silently enabled.
- [ ] Perform a test update check and verify the updater's checksum validation and rollback behavior without using live production data.
- [ ] Confirm employee, attendance, device configuration, and backup data remain intact after app replacement and restart.
- [ ] Record logs/screenshots and the result for each check; mark unavailable physical-device checks as not run rather than passed.


## 4. Post-delivery physical K50 acceptance

Perform these checks after the initial tester build is handed over, when the physical K50 and its network are available. These checks are user acceptance, not an initial-delivery blocker. CI mock/fixture tests must cover the core software paths, but they cannot prove communication with the actual device.

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
- [ ] On a disposable copy of a legacy database that predates `staff.name_source`, start the background monitor before opening the GUI; confirm its additive migration preserves every existing employee name.
- [ ] Run foreground Fetch Attendance against that database; confirm a legacy/profile-managed name is not replaced and a new device user is created with the device-provided name.
- [ ] Change a device-managed employee name on the device and sync again; confirm the device name refreshes while it remains device-managed.
- [ ] Save a custom name in Employee Management, then repeat foreground fetch and background monitor sync; confirm neither path overwrites the profile name or changes its department, designation, joining date, active status, or status history.
- [ ] Confirm the fetch success/warning summary reports device users processed, attendance records read, and new records saved; it must not claim that every employee name was changed or synced.
- [ ] Confirm employee history and linked attendance remain associated with the correct employee after edits.
- [ ] Test duplicate employee identifiers and invalid required fields.
- [ ] Verify dashboard totals against the underlying attendance records for a known date range.
- [ ] Export Excel and confirm employee names/statuses beginning with `=`, `+`, `-`, or `@` remain literal text rather than formulas.
- [ ] Export PDF and confirm English report labels, Latin-script employee names, long IDs, and status values render safely and legibly.
- [ ] Verify CSV/PDF/Excel exports against the same known records.
- [ ] Confirm backup and restore preserve employees, attendance, schedules, leave, and settings.
- [ ] Test backup restore while the background monitor is enabled; confirm maintenance locking prevents partial or inconsistent writes.

## 6. Evidence and sign-off

For each manual test, record the result, date, operator, machine, exact commit, workflow run, artifact ID, and any log/screenshot reference.

### Historical automated CI and packaging evidence — superseded PR #11 snapshot `a9ba51a2366bf95d8a8c98b676009e716f91a015`

> Historical evidence only. The 4059ab6/a9ba51a snapshots below are superseded by section 8, which records the current updater-worker regression coverage, exact-head CI and tester artifacts.

The latest application/test changes before this snapshot are in `d2a9e274` (device-sync completion messaging and its regression test). Commits `c7630b6` and `a9ba51a` update only this manual-acceptance document; they do not change application or test sources. Both workflow runs below validate the exact PR snapshot `a9ba51a2366bf95d8a8c98b676009e716f91a015`.

- Validation run [#44094814799](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44094814799) validates exact head `a9ba51a2366bf95d8a8c98b676009e716f91a015`:
  - Windows: **206 tests run, 204 passed, 2 skipped**.
  - Intel macOS: **206 tests run, 204 passed, 2 skipped**.
  - Apple Silicon: **206 tests run, 204 passed, 2 skipped**.
  - All executed tests passed; the two skips on each platform are platform/host-permission-specific.
- Packaging run [#44094814779](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44094814779) validates the same exact head. Windows, Intel macOS and Apple Silicon package jobs and all artifact uploads succeeded. The `publish` job was skipped for this pull-request event; no release was published.
- All five artifacts below were verified present and unexpired. They were created on 17 November 2026 and expire **15 February 2027 at 13:38:51 UTC**. SHA-256 values are GitHub's artifact archive digests, not separately calculated hashes of the extracted installers.

| Artifact | Commit | Download | Size | Created (UTC) | Expires (UTC) | Archive SHA-256 |
|---|---|---|---:|---|---|---|
| Windows installer `release-windows` | `a9ba51a` | [#14332379690](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44094814779/artifacts/14332379690) | 48,457,638 B | 13:41:06 | 15 Feb 2027 13:38:51 | `7908746eef8fa8fe357392e5b4f080f6008eb463f950419e5b842cdcfbd255f9` |
| Apple Silicon app ZIP `release-macos-apple-silicon` | `a9ba51a` | [#14333382021](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44094814779/artifacts/14333382021) | 37,153,406 B | 13:39:55 | 15 Feb 2027 13:38:51 | `fa3a28c65f4b2ebf22a82c80eaae69467adc35b9c6f56cfe65f668d3d6adac89` |
| Intel macOS app ZIP `release-macos-intel` | `a9ba51a` | [#14333257384](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44094814779/artifacts/14333257384) | 39,837,072 B | 13:40:37 | 15 Feb 2027 13:38:51 | `0cb1dcd1a594399340edaa49adb7204e0a5b62cc37076c1d8eea4cf96abbd00f` |
| Intel macOS installer `release-macos-intel-installer` | `a9ba51a` | [#14332084727](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44094814779/artifacts/14332084727) | 39,814,921 B | 13:40:41 | 15 Feb 2027 13:38:51 | `4ee33ac46f9b91982ab4675154197c3b0edb5d07b6345a4c6d9aa14861645ded` |
| Intel icon patch `release-macos-intel-icon-patch` | `a9ba51a` | [#14334250120](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44094814779/artifacts/14334250120) | 92,952 B | 13:40:42 | 15 Feb 2027 13:38:51 | `3a08715264e25f2303124cc6d4b97ffec07e4729d50cd53da2704196b34adf91` |

These are temporary CI artifacts for testing, not published release assets. Apple Silicon currently produces an application ZIP rather than a `.pkg` installer. The successful builds do not establish Windows Authenticode signing or Apple Developer ID signing/notarization.

The employee-name ownership regression coverage verifies that legacy rows migrate as profile-managed, new device users are device-managed, device-managed names can refresh, and saving a profile switches ownership so later device syncs preserve the curated name. The foreground fetch summary accurately reports device users processed rather than implying every profile name was overwritten. These automated tests passed on all three validation runners. The real-machine GUI/monitor acceptance steps in section 5 remain **not run** until tested on a disposable machine with a K50 device.

| Gate | Result | Evidence |
|---|---|---|
| Windows clean install | Not run | Disposable Windows 10/11 VM required |
| Windows v1.3.0 → v1.4 upgrade | Not run | Disposable Windows 10/11 VM required |
| Windows monitor state preservation | Automated regression passed; manual not run | Exact-head validation #44094814799 |
| Windows missing scheduled-task detection | Windows PowerShell integration passed; full installer scenario not run | Exact-head validation #44094814799 |
| Windows updater timeout/rollback | Automated regression passed; manual fault injection not run | Exact-head validation #44094814799 |
| Windows direct-installer PowerShell timeout/termination | Automated regression passed; manual fault injection not run | Exact-head validation #44094814799 |
| Windows PowerShell descendant-process cleanup | Windows integration test passed; manual installer fault injection not run | Exact-head validation #44094814799 |
| Windows uninstall/data preservation | Not run | Disposable Windows 10/11 VM required |
| Intel macOS clean install | Not run | Physical Mac or disposable VM required |
| Intel macOS v1.3.0 → v1.4 upgrade | Not run | Physical Mac or disposable VM required |
| macOS LaunchAgent stop/restart/rollback | Not run | Physical Mac or disposable VM required |
| Intel icon patch | Not run | Physical Intel Mac required |
| Apple Silicon/ARM64 build and hardware test | Out of scope for initial v1.4 | No initial-delivery artifact or runner required |
| Physical K50 discovery/fetch/sync | Post-delivery user acceptance; not an initial-delivery blocker | User's K50 device and network; record results after handoff |
| Employee profile/name ownership and dashboard/Excel/PDF regression | Automated suite passed; end-to-end GUI checks not run | Exact-head validation #44094814799 |
| Backup/restore with monitor enabled | Automated regression passed; live monitor/restore acceptance not run | Exact-head validation #44094814799 |

## 7. Distribution signing and notarization decision

The current CI workflow builds Windows and macOS artifacts but does not include Windows Authenticode signing or Apple Developer ID signing/notarization steps. Successful compilation and artifact upload do not establish publisher identity or Gatekeeper/SmartScreen acceptance.

- [ ] Release owner decides whether signed Windows distribution is required for v1.4.0.
- [ ] Release owner decides whether Developer ID signing and Apple notarization are required for the Intel macOS distribution.
- [ ] If signing is required, configure credentials only as protected GitHub Actions secrets; never commit certificates, private keys, passwords, or notarization credentials.
- [ ] Add platform-specific signing/notarization steps and verify the final distributed binaries/packages (not only intermediate build outputs).
- [ ] Record certificate identity, notarization result/ticket where applicable, and final installer/package checksums.
- [ ] If signing is intentionally deferred, document the accepted unsigned-distribution warning and the supported Windows and Intel macOS installation instructions before publication.


**Initial v1.4 delivery gate:** Windows x64 and Intel macOS exact-head validation and packaging must pass; the corresponding artifacts must be present and verified; and required installer, updater/rollback, and database-preservation checks must be completed or explicitly recorded as outstanding manual gates. Apple Silicon/ARM64 is excluded from this delivery and cannot block it. The physical K50 checks in section 4 are post-delivery user acceptance and must be recorded separately, not treated as a prerequisite to handing over the initial tester build. A skipped or unavailable **required Windows or Intel macOS** job remains an open gate.


## 8. Current updater release-check worker verification — 18 November 2026

**Code/test commit:** `99312cb9479b59da098e00a0f68274641cfc1baa` on `feature/v1.4-employee-management`.

The new `k50_attendance_build/test_update_check_worker.py` exercises the actual background release-check worker without opening a GUI or making a network request. Five regression tests cover:
- malformed release tags never reaching the update-offer callback;
- Windows selecting `SCAFA_Workforce_Setup.exe` and requiring `checksums.txt`;
- Intel macOS selecting `SCAFA_Workforce_macOS_intel.zip` and requiring `checksums.txt`;
- missing platform packages or checksum manifests failing closed; and
- equal/older releases not generating an update offer.

### Exact-code-head validation and packaging

Both workflows below were run against the exact code/test commit `99312cb9479b59da098e00a0f68274641cfc1baa`.

- Validation [run #44159327821](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44159327821): Windows and Intel macOS both passed **228 tests: 226 passed, 2 skipped**. Test, application/helper build, and all executed steps passed on both platforms.
- Packaging [run #44159327902](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44159327902): Windows and Intel macOS build and artifact-upload jobs passed. The publish job was skipped for this pull-request event; no release was published.

### Verified tester artifacts

All four artifacts are present, unexpired, and associated by GitHub metadata with exact code/test commit `99312cb9479b59da098e00a0f68274641cfc1baa` and packaging run #44159327902. Created 18 November 2026 UTC; expiry **15 February 2027 at 19:30:36 UTC**.

| Artifact | Artifact ID / download | Size | Created (UTC) |
|---|---|---:|---|
| Windows installer `release-windows` | [#14362552497](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44159327902/artifacts/14362552497) | 48,461,403 B | 19:32:47 |
| Intel macOS app ZIP `release-macos-intel` | [#14362053097](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44159327902/artifacts/14362053097) | 39,843,224 B | 19:33:09 |
| Intel macOS installer `release-macos-intel-installer` | [#14361544044](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44159327902/artifacts/14361544044) | 39,828,228 B | 19:33:14 |
| Intel icon patch `release-macos-intel-icon-patch` | [#14361968327](https://github.com/NaveedQamar1/Paisa-Laya/actions/runs/44159327902/artifacts/14361968327) | 92,952 B | 19:33:16 |

These are temporary GitHub Actions artifacts, not published release assets. The current PR head may advance with this documentation-only update; the CI evidence above applies to the exact code/test commit shown, not to a later documentation-only commit.

The automated worker tests do **not** prove a real update has been installed. Windows and Intel macOS update-helper execution, monitor stop/restart, database/settings preservation, successful relaunch, rollback, clean install and v1.3.0-to-v1.4 upgrade remain manual release gates. Do not use the in-app Update button until those gates are verified.
