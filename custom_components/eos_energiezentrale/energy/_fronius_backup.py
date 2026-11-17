"""Bounded Solar API backup status, independent of SunSpec power telemetry."""
from datetime import timedelta
from time import monotonic

from .clients import base_url, request
from .contracts import PowerSupplyReading
from .domain import instant
from .power_supply import checked_supply


class FroniusBackup:
    def __init__(self, url):
        self.url = base_url(url)+'/solar_api/v1/GetPowerFlowRealtimeData.fcgi'
        self.last_probe = None
        self.value = None
        self.error = None
        self.supported = False

    def read(self, now):
        clock = monotonic()
        if self.last_probe is None or clock-self.last_probe >= 30:
            self.last_probe = clock
            self.error = None
            self.value = PowerSupplyReading('unknown', None) if self.supported else None
            try:
                payload = request(self.url)
                head = payload['Head']
                if type(head['Status']['Code']) is not int or head['Status']['Code'] != 0:
                    raise ValueError('Solar API status request failed')
                site = payload['Body']['Data']['Site']
                if not isinstance(site, dict):
                    raise ValueError('Solar API site data is invalid')
                if 'BackupMode' in site:
                    self.supported = True
                    if type(site['BackupMode']) is not bool:
                        raise ValueError('Solar API backup state must be boolean')
                    stamp = instant(head.get('Timestamp'))
                    completed = now+timedelta(seconds=monotonic()-clock)
                    if stamp is None or not -5 <= (completed-stamp).total_seconds() < 120:
                        raise ValueError('Solar API backup timestamp is invalid')
                    self.value = PowerSupplyReading('backup' if site['BackupMode'] else 'grid', min(stamp, now))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.error = error
                self.value = PowerSupplyReading('unknown', None)
        return checked_supply(self.value, now)
