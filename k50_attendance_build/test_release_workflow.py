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
            r"$releaseTag -notmatch '^scafa-v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$') {",
            self.workflow,
        )
        self.assertEqual(
            self.workflow.count(
                '[[ ! "$RELEASE_TAG" =~ ^scafa-v[0-9]+'
            ),
            2,
        )
        self.assertEqual(self.workflow.count("release_tag must match scafa-vMAJOR.MINOR.PATCH"), 3)


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


if __name__ == "__main__":
    unittest.main()
