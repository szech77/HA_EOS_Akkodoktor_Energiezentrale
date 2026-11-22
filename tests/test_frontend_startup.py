"""A UI update must invalidate every dependent asset as one build."""
import unittest
from custom_components.eos_energiezentrale.frontend import asset_version, vue_bundle_present
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
            current=asset_version(directory)
            (directory/'logo.svg').write_text('<svg/>')
            self.assertNotEqual(asset_version(directory),current)
            current=asset_version(directory)
            (directory/'vue').mkdir()
            (directory/'vue'/'eos-vue.js').write_text('bundle one')
            self.assertNotEqual(asset_version(directory),current)
            current=asset_version(directory)
            (directory/'vue'/'eos-vue.js').write_text('bundle two')
            self.assertNotEqual(asset_version(directory),current)

    def test_the_built_vue_bundle_is_detected_in_its_subfolder(self):
        with temporary_project_directory() as directory:
            self.assertFalse(vue_bundle_present(directory))
            (directory/'vue').mkdir()
            (directory/'vue'/'eos-vue.js').write_text('bundle')
            self.assertTrue(vue_bundle_present(directory))
