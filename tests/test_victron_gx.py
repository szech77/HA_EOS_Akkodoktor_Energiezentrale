"""Run the entire ESS behavior contract for the official GX plugin as well."""
import test_victron_ha as shared


class VictronGXTests(shared.VictronTests):
    plugin_id='victron_gx'

    def test_official_and_hacs_plugins_are_distinct_and_both_discovered(self):
        self.assertEqual(self.driver.info.identifier,'victron_gx')
        self.assertIn('official',self.driver.info.name)
        self.assertIn('victron_ha',shared.BATTERY_DRIVERS)
