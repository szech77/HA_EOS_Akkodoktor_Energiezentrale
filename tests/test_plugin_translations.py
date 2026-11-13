"""Every bundled plugin's native form can be translated without changing values."""
import json
from pathlib import Path

from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS, INVERTER_DRIVERS, WALLBOX_DRIVERS
from custom_components.eos_energiezentrale.plugin_forms import plugin_object


def test_all_bundled_plugin_fields_and_choices_have_german_and_english_translations():
    root=Path(__file__).resolve().parents[1]/'custom_components'/'eos_energiezentrale'
    english=json.loads((root/'translations/en.json').read_text(encoding='utf-8'))
    german=json.loads((root/'translations/de.json').read_text(encoding='utf-8'))
    assert json.loads((root/'strings.json').read_text(encoding='utf-8'))==english
    for registry in (BATTERY_DRIVERS,INVERTER_DRIVERS,WALLBOX_DRIVERS):
        for factory in registry.values():
            if not factory.configuration: continue
            control,_=plugin_object(factory)
            config=control.serialize()['selector']['object']
            for resource in (english,german):
                translated=resource['selector'][config['translation_key']]['fields']
                assert set(translated)==set(config['fields'])
                assert all(field['name'].strip() for field in translated.values())
                for field in factory.configuration:
                    descriptor=config['fields'][field.key]
                    # Keep the descriptor's English label if client translations are unavailable.
                    assert descriptor['label']==field.label
                    if field.kind=='choice':
                        choice=descriptor['selector']['select']
                        options=resource['selector'][choice['translation_key']]['options']
                        assert set(options)==set(field.choices)
                        assert choice['options']==list(field.choices)
                        assert all(label.strip() for label in options.values())
