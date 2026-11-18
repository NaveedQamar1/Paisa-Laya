"""Regression tests for release workflow input handling."""
from pathlib import Path
import unittest


class ReleaseWorkflowInputSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "scafa-release.yml"
        )
        cls.workflow = workflow_path.read_text(encoding="utf-8")

    def test_dispatch_input_is_passed_through_environment_not_shell_source(self):
        self.assertNotIn(
            '$releaseTag = "${{ github.event.inputs.release_tag }}"',
            self.workflow,
        )
        self.assertNotIn(
            'RELEASE_TAG="${{ github.event.inputs.release_tag }}"',
            self.workflow,
        )
        self.assertEqual(
            self.workflow.count(
                "SCAFA_RELEASE_TAG_INPUT: ${{ github.event.inputs.release_tag }}"
            ),
            3,
        )
        self.assertIn("$releaseTag = $env:SCAFA_RELEASE_TAG_INPUT", self.workflow)
        self.assertEqual(
            self.workflow.count('RELEASE_TAG="${SCAFA_RELEASE_TAG_INPUT:-}"'),
            2,
        )

    def test_release_tag_input_is_validated_before_package_and_release_use(self):
        self.assertIn(
            r"$releaseTag -notmatch '^scafa-v[0-9]+\.[0-9]+\.[0-9]+$') {",
            self.workflow,
        )
        self.assertEqual(
            self.workflow.count(
                '[[ ! "$RELEASE_TAG" =~ ^scafa-v[0-9]+'
            ),
            2,
        )
        self.assertEqual(
            self.workflow.count(
                "release_tag must exactly match APP_VERSION as scafa-vMAJOR.MINOR.PATCH."
            ),
            3,
        )


    def test_package_version_must_match_application_version(self):
        self.assertIn(
            '$appVersion = $versionLine.Matches[0].Groups[1].Value',
            self.workflow,
        )
        self.assertIn('if ($releaseTag -ne "scafa-v$appVersion")', self.workflow)
        self.assertIn('if [[ "$RELEASE_TAG" != "scafa-v$APP_VERSION" ]]', self.workflow)
        self.assertIn('VERSION="$APP_VERSION"', self.workflow)
        self.assertIn(
            r'& $iscc "/DMyAppVersion=$version" "k50_attendance_build\installer\SCAFA_Workforce.iss"',
            self.workflow,
        )
        self.assertIn(
            'pkgbuild --component dist/SCAFA_Workforce.app --install-location /Applications --scripts "$MACOS_INSTALLER_SCRIPTS" --identifier pk.scafa.workforce --version "$VERSION"',
            self.workflow,
        )
        self.assertIn(
            'pkgbuild --nopayload --scripts icon-patch-scripts --identifier pk.scafa.workforce.iconpatch --version "$VERSION"',
            self.workflow,
        )
        installer_script = (
            Path(__file__).with_name("installer") / "SCAFA_Workforce.iss"
        ).read_text(encoding="utf-8")
        self.assertIn("AppVersion={#MyAppVersion}", installer_script)
        self.assertNotIn('optionally with a prerelease suffix', self.workflow)
        self.assertEqual(
            self.workflow.count(
                "release_tag must exactly match APP_VERSION as scafa-vMAJOR.MINOR.PATCH."
            ),
            3,
        )

    def test_release_publication_requires_an_explicit_versioned_tag_ref(self):
        publish = self.workflow.split("  publish:", 1)[1]
        self.assertIn(
            "if: startsWith(github.ref, 'refs/tags/scafa-v')",
            publish,
        )
        self.assertNotIn("github.event_name != 'pull_request'", publish)
        self.assertNotIn("refs/heads/main", publish)

    def test_tag_builds_use_the_exact_pushed_tag(self):
        self.assertIn(
            "$env:GITHUB_REF -like 'refs/tags/scafa-v*'",
            self.workflow,
        )
        self.assertIn(
            "$releaseTag -ne $env:GITHUB_REF.Substring('refs/tags/'.Length)",
            self.workflow,
        )
        self.assertEqual(
            self.workflow.count('[[ "$GITHUB_REF" == refs/tags/scafa-v* ]]'),
            2,
        )
        self.assertEqual(
            self.workflow.count('RELEASE_TAG="${GITHUB_REF#refs/tags/}"'),
            2,
        )


    def test_release_write_permission_is_limited_to_publisher(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        publish = self.workflow.split("  publish:", 1)[1]
        self.assertIn("permissions:\n      contents: write", publish)
        self.assertNotIn("contents: write", self.workflow.split("\njobs:\n", 1)[0])

    def test_release_actions_are_pinned_to_immutable_revisions(self):
        for action in (
            "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09",
            "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
            "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f",
            "actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131",
        ):
            with self.subTest(action=action):
                self.assertIn(action, self.workflow)
        self.assertNotIn("actions/checkout@v4", self.workflow)
        self.assertNotIn("actions/setup-python@v5", self.workflow)
        self.assertNotIn("actions/upload-artifact@v4", self.workflow)
        self.assertNotIn("actions/download-artifact@v4", self.workflow)


    def test_initial_delivery_ci_matrix_matches_supported_platforms(self):
        validation_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "scafa-validation.yml"
        )
        validation_workflow = validation_path.read_text(encoding="utf-8")
        for workflow in (self.workflow, validation_workflow):
            with self.subTest(workflow="release" if workflow is self.workflow else "validation"):
                self.assertIn("runner: macos-15-intel", workflow)
                self.assertNotIn("apple-silicon", workflow)
                self.assertNotIn("runner: macos-15\n", workflow)
                self.assertIn("runs-on: windows-latest", workflow)

    def test_build_workflow_uses_pinned_pillow_from_requirements(self):
        requirements = (
            Path(__file__).with_name("requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        pillow_requirements = [
            line.strip()
            for line in requirements
            if line.strip().lower().startswith("pillow")
        ]
        self.assertEqual(pillow_requirements, ["Pillow==13.0.0"])
        self.assertNotIn("python -m pip install pillow", self.workflow)
        self.assertEqual(
            self.workflow.count(
                "python -m pip install -r k50_attendance_build/requirements.txt"
            ),
            2,
        )
        self.assertEqual(
            self.workflow.count("python -m pip install --upgrade pip==26.3"),
            2,
        )
        self.assertNotIn("python -m pip install --upgrade pip\\n", self.workflow)


    def test_windows_uninstaller_helper_is_copied_into_the_installed_application_tree(self):
        windows_build = self.workflow.split(
            "      - name: Build Windows installer", 1
        )[1].split("\n  macos:", 1)[0]
        installer_script = (
            Path(__file__).with_name("installer")
            / "SCAFA_Workforce.iss"
        ).read_text(encoding="utf-8")

        helper_copy = (
            "Copy-Item dist/scafa-updater.exe "
            "dist/SCAFA_Workforce/scafa-updater.exe -Force"
        )
        self.assertIn(helper_copy, windows_build)
        self.assertLess(
            windows_build.index(helper_copy),
            windows_build.index("& $iscc"),
        )
        self.assertIn(
            r'Source: "..\..\dist\SCAFA_Workforce\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs',
            installer_script,
        )
        self.assertIn(
            r"MonitorHelperPath := ExpandConstant('{app}\scafa-updater.exe')",
            installer_script,
        )
        self.assertIn(
            r'Source: "..\..\dist\scafa-updater.exe"; Flags: dontcopy',
            installer_script,
        )

    def test_windows_installer_compiler_is_pinned_to_the_verified_version(self):
        # The latest successful Windows package log reported Inno Setup 6.7.1.
        # Pin it so future Chocolatey releases cannot silently change installer output.
        self.assertIn(
            "choco install innosetup --version=6.7.1 --allow-downgrade --yes --no-progress",
            self.workflow,
        )

if __name__ == "__main__":
    unittest.main()
