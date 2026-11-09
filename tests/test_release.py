"""Release requirements tested through metadata and the GitHub API contract."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from test_energy import temporary_project_directory


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_tool", ROOT / "tools/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

COMMIT = "a" * 40
NOTES = """### Features

- Adds a feature.

### Bugfixes

- Fixes a charging problem.

### Breaking Changes

- None.

### Security

- None.
"""


class ReleaseRequirements(unittest.TestCase):
    def project(self, root, notes=NOTES, version="0.1.3"):
        addon = root / "custom_components/eos_energiezentrale"
        addon.mkdir(parents=True)
        (addon / "manifest.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        changelog = "# Changelog\n\n## " + version + "\n\n" + notes + "\n## 0.1.2\n\nPrevious changes.\n"
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    def test_release_notes_contain_only_the_selected_version(self):
        with temporary_project_directory() as root:
            self.project(root)
            version, notes = release.release_metadata(root)
        self.assertEqual(version, "0.1.3")
        self.assertEqual(notes, NOTES)
        self.assertNotIn("Previous changes", notes)

    def test_missing_categories_stop_release(self):
        for section in release.SECTIONS:
            with self.subTest(section=section), temporary_project_directory() as root:
                self.project(root, NOTES.replace("### " + section, "### Other"))
                with self.assertRaises(ValueError):
                    release.release_metadata(root)

    def test_version_without_changelog_cannot_be_released(self):
        with temporary_project_directory() as root:
            self.project(root)
            (root / "custom_components/eos_energiezentrale/manifest.json").write_text('{"version":"0.2.0"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                release.release_metadata(root)

    def test_release_targets_exact_published_commit(self):
        github = Mock()
        github.tag_commit.return_value = None
        github.request.side_effect = [None, {"id": 123, "tag_name": "v0.1.3"}]
        result = release.publish_release(github, "0.1.3", NOTES, COMMIT)
        self.assertEqual(result["tag_name"], "v0.1.3")
        data = github.request.call_args.kwargs or github.request.call_args.args[2]
        self.assertEqual(data["target_commitish"], COMMIT)
        self.assertEqual(data["body"], NOTES)
        self.assertFalse(data["draft"])

    def test_existing_version_on_another_commit_is_never_overwritten(self):
        github = Mock()
        github.tag_commit.return_value = "b" * 40
        with self.assertRaises(ValueError):
            release.publish_release(github, "0.1.3", NOTES, COMMIT)
        github.request.assert_not_called()

    def test_retry_is_safe_and_changed_published_notes_are_rejected(self):
        github = Mock()
        github.tag_commit.return_value = COMMIT
        existing = {"id": 123, "body": NOTES, "draft": False, "prerelease": False}
        github.request.return_value = existing
        self.assertEqual(release.publish_release(github, "0.1.3", NOTES, COMMIT), existing)
        self.assertTrue(all(call.args[0].startswith("/releases/tags/") for call in github.request.call_args_list))
        with self.assertRaises(ValueError):
            release.publish_release(github, "0.1.3", NOTES + "\nChanged.", COMMIT)
