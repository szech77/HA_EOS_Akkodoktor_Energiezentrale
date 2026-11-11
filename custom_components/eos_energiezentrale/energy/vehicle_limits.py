"""Translate live charger limits into conservative EOS charging profiles."""
from math import floor


def optional_charger(driver):
    return getattr(getattr(driver, 'features', None), 'optional_connection', False) is True


def charging_profile(box, driver, options, daily, connected):
    if box.max_phases is None or box.maximum is None or box.nominal_voltage is None:
        return (None, None, (0.,), False)
    phases = box.max_phases if daily['phase_auto'] and driver.features.phase_switching else box.phases
    if phases not in (1,3):
        return (None, None, (0.,), False)
    current = min(box.maximum, options['max_current_a'])
    maximum = current * phases * box.nominal_voltage
    allowed = (1,3) if phases == 3 and daily['phase_auto'] and driver.features.phase_switching else (phases,)
    minimum = 6 * min(allowed) * box.nominal_voltage
    powers = {0.}
    for count in allowed:
        for amps in (*range(6,floor(current)+1), current):
            powers.add(amps * count * box.nominal_voltage)
    rates = tuple(sorted({round(value/maximum,9) for value in powers}))
    active = bool(connected and box.watts is not None and box.status in ('connected','charging','wakeup'))
    return (maximum, minimum, rates if active else (0.,), active)
