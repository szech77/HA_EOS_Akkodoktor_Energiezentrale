"""Measured values the Energiezentrale owns, written to the EOS measurement store.

EOS takes the initial SoC of every battery and electric vehicle for its optimisation from the
measurement "<device_id>-soc-factor" and assumes 0 % without a fresh value. Charge and
discharge power describe the device's operating point. Only values this integration has
validated are sent; a missing or invalid value is never replaced by zero.
"""
from dataclasses import dataclass
import logging
from math import isfinite

_LOGGER = logging.getLogger(__name__)

# Every key is refreshed at least this often, so EOS always finds a recent value.
SYNC_INTERVAL_S = 60
# A SoC change of at least this factor is sent at once (one percentage point).
SOC_STEP = 0.01
# The accepted keys follow the EOS device configuration; re-read them now and then.
KEYS_INTERVAL_S = 900


@dataclass(frozen=True)
class Sample:
    key: str
    value: float


def device_samples(resource, *, soc=None, charge_w=None, discharge_w=None):
    """EOS measurement samples of one battery or vehicle resource from validated readings.

    ``soc`` is in percent (0–100); EOS stores it as a factor. Powers are in W and not negative.
    """
    if not isinstance(resource, str) or not resource:
        return []
    result = []
    if _finite(soc) and 0 <= soc <= 100:
        result.append(Sample(f'{resource}-soc-factor', round(soc / 100, 4)))
    for suffix, watts in (('charge-power-w', charge_w), ('discharge-power-w', discharge_w)):
        if _finite(watts) and watts >= 0:
            result.append(Sample(f'{resource}-{suffix}', round(watts, 1)))
    return result


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


class MeasurementSync:
    """Send due samples to EOS; keys EOS does not know are skipped and reported once."""

    def __init__(self):
        self.keys = None
        self.keys_at = None
        self.supported = None
        self.missing = frozenset()
        self.sent = {}
        self.sent_at = None
        self.failed_at = None

    def due(self, sample, clock):
        previous = self.sent.get(sample.key)
        if previous is None:
            return True
        value, at = previous
        if clock - at >= SYNC_INTERVAL_S:
            return True
        return sample.key.endswith('-soc-factor') and abs(sample.value - value) >= SOC_STEP

    def sync(self, eos, samples, now, clock):
        """Return True after sending, False when EOS has no measurement API, None when idle.

        Errors propagate; after a failure the next attempt waits one interval so a failing
        EOS is not flooded every control cycle.
        """
        if self.failed_at is not None and clock - self.failed_at < SYNC_INTERVAL_S:
            return None
        try:
            return self._sync(eos, samples, now, clock)
        except Exception:
            self.failed_at = clock
            raise

    def _sync(self, eos, samples, now, clock):
        if self.keys_at is None or clock - self.keys_at >= KEYS_INTERVAL_S:
            keys = eos.measurement_keys()
            self.keys_at = clock
            # Only a key set counts; None (or anything else) means EOS offers no measurement API.
            supported = isinstance(keys, (set, frozenset))
            if supported != self.supported and not supported:
                _LOGGER.info('EOS measurement API unavailable (eos_measurements_unsupported); SoC is not sent to EOS')
            self.supported, self.keys = supported, frozenset(keys) if supported else frozenset()
        self.failed_at = None
        if not self.supported:
            return False
        missing = frozenset(sample.key for sample in samples if sample.key not in self.keys)
        if missing != self.missing:
            if missing:
                # Keys are built from configured EOS resource ids, never from measured values.
                _LOGGER.info('EOS measurement keys not configured in EOS (eos_measurement_keys_missing): %s', ', '.join(sorted(missing)))
            self.missing = missing
        pending = [sample for sample in samples if sample.key in self.keys and self.due(sample, clock)]
        if not pending:
            return None
        for sample in pending:
            eos.put_measurement(sample.key, sample.value, now)
            self.sent[sample.key] = (sample.value, clock)
        self.sent_at = now
        return True

    def diagnostics(self):
        """Which keys are sent, which EOS does not know; no values."""
        return {'supported': self.supported, 'keys': sorted(self.sent), 'missing': sorted(self.missing),
                'sent_at': self.sent_at.isoformat() if self.sent_at else None}
