"""Translate live charger limits into conservative EOS charging profiles."""
from dataclasses import replace
from math import floor


def optional_charger(driver):
    return getattr(getattr(driver, 'features', None), 'optional_connection', False) is True


def vehicle_phases(options):
    """Phases the vehicle can charge on: 1 for a single-phase on-board charger, otherwise 3."""
    return 1 if options.get('max_phases', 3) == 1 else 3


def switchable(driver):
    return getattr(getattr(driver, 'features', None), 'phase_switching', False) is True


def vehicle_box(box, driver, options):
    """The wallbox reading as the vehicle uses it.

    A single-phase vehicle draws on one phase even when the wallbox supplies three. A
    wallbox that can switch phases is kept on one phase by the regulation; one that
    cannot is treated as single-phase, so power and current are calculated for the
    phase the vehicle actually uses.
    """
    if vehicle_phases(options) == 3:
        return box
    if switchable(driver):
        return replace(box, max_phases=1) if box.max_phases is not None else box
    return replace(box, phases=1 if box.phases is not None else None,
                   max_phases=1 if box.max_phases is not None else None)


def charging_profile(box, driver, options, daily, connected):
    if box.max_phases is None or box.maximum is None or box.nominal_voltage is None:
        return (None, None, (0.,), False)
    phases = box.max_phases if daily['phase_auto'] and driver.features.phase_switching else box.phases
    if phases in (1,3) and vehicle_phases(options) == 1:
        phases = 1
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
