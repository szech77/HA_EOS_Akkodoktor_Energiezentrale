"""A UI update must invalidate every dependent asset as one build."""
import unittest
from custom_components.eos_energiezentrale.frontend import asset_version
from test_energy import temporary_project_directory


class FrontendBuildRequirements(unittest.TestCase):
    def test_file_content_changes_invalidate_ui_build_even_if_filenames_stay_the_same(self):
        with temporary_project_directory() as directory:
            (directory/'chart-data.js').write_text('old helper')
            (directory/'app.js').write_text('old app')
            original=asset_version(directory)
            self.assertEqual(asset_version(directory),original)
            (directory/'chart-data.js').write_text('new helper')
            self.assertNotEqual(asset_version(directory),original)
            current=asset_version(directory)
            (directory/'style.css').write_text('new style')
            self.assertNotEqual(asset_version(directory),current)
