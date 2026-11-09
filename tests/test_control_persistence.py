"""Persistent user intent versus temporary stop, device faults and corrupt storage."""
import unittest
from unittest.mock import Mock, patch

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.settings import Configuration
from test_energy import temporary_project_directory


class ControlPersistenceRequirements(unittest.TestCase):
    def test_explicit_enable_survives_temporary_stop_and_settings_updates(self):
        with temporary_project_directory() as directory:
            config = Configuration(dict(DEFAULTS),Mock(),directory)
            app = Controller(Mock(),config)
            self.assertFalse(app.armed)
            app.set_armed(True)
            config.update({**config.daily,"pv":True})
            app.set_armed(False,persist=False)
            self.assertFalse(app.armed)
            restored = Controller(Mock(),Configuration(dict(DEFAULTS),Mock(),directory))
            self.assertTrue(restored.armed)
            self.assertTrue(restored.restore_pending)

    def test_explicit_off_is_kept_even_if_device_release_fails(self):
        with temporary_project_directory() as directory:
            config = Configuration(dict(DEFAULTS),Mock(),directory)
            ha = Mock()
            app = Controller(ha,config)
            app.set_armed(True)
            app.owned = True
            ha.states.side_effect = OSError("device unavailable")
            with self.assertRaises(OSError):
                app.set_armed(False)
            self.assertFalse(app.armed)
            self.assertTrue(app.owned)
            self.assertFalse(Controller(Mock(),Configuration(dict(DEFAULTS),Mock(),directory)).armed)

    def test_failed_enable_save_does_not_arm_controller(self):
        with temporary_project_directory() as directory:
            config = Configuration(dict(DEFAULTS),Mock(),directory)
            app = Controller(Mock(),config)
            with patch('custom_components.eos_energiezentrale.energy.settings.save',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    app.set_armed(True)
            self.assertFalse(app.armed)
            self.assertFalse(config.control_enabled)
            self.assertIn('control_persistence',app.errors)

    def test_failed_disable_save_still_attempts_release_and_reports_persistence_failure(self):
        with temporary_project_directory() as directory:
            config = Configuration(dict(DEFAULTS),Mock(),directory)
            app = Controller(Mock(),config)
            app.set_armed(True)
            app.owned = True
            with (patch('custom_components.eos_energiezentrale.energy.settings.save',side_effect=OSError('disk full')),
                  patch.object(app,'release') as release):
                with self.assertRaises(OSError):
                    app.set_armed(False)
            self.assertFalse(app.armed)
            release.assert_called_once()
            self.assertIn('control_persistence',app.errors)

    def test_invalid_persisted_state_never_enables_control(self):
        for payload in ('{"enabled":"on"}', '{"enabled":1}', '{}', 'true', '{broken'):
            with self.subTest(payload=payload), temporary_project_directory() as directory:
                (directory/'control.json').write_text(payload,encoding='utf-8')
                with self.assertRaises(ValueError):
                    Configuration(dict(DEFAULTS),Mock(),directory)
