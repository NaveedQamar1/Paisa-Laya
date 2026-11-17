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
        self.assertIn("$releaseTag -notmatch '^scafa-v[0-9]+", self.workflow)
        self.assertEqual(
            self.workflow.count(
                '[[ ! "$RELEASE_TAG" =~ ^scafa-v[0-9]+'
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
