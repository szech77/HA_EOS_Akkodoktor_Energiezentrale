"""The PV report: production per bin by use, the forecast for the rest of the period, notable bins."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.eos_energiezentrale.energy.accounting import empty
from custom_components.eos_energiezentrale.energy.power_profile import power_profile
from custom_components.eos_energiezentrale.energy.pv_report import pv_forecast
from custom_components.eos_energiezentrale.energy.report_values import report_values

ZONE = 'Europe/Berlin'
# 2026-11-18 12:30 local time (UTC+1).
NOW = datetime(2026, 11, 18, 11, 30, tzinfo=timezone.utc)


def forecast(start, hours, watts=2000):
    return [{'time': (start + timedelta(hours=index)).isoformat(),
             'end': (start + timedelta(hours=index + 1)).isoformat(), 'solar': watts} for index in range(hours)]


def test_day_forecast_counts_only_the_future_per_hour_and_gives_the_power_curve():
    rows = forecast(datetime(2026, 11, 18, 10, tzinfo=timezone.utc), 30)
    report = {'period': 'day', 'date': '2026-11-18', 'end': '2026-11-19'}
    result = pv_forecast(rows, report, NOW, ZONE)
    bins = {row['time']: row['kwh'] for row in result['bins']}
    # 11:00 UTC is half over: 1 kWh remains; past hours are not forecast; the day ends at 23:00 UTC.
    assert '2026-11-18T10:00:00+00:00' not in bins
    assert bins['2026-11-18T11:00:00+00:00'] == pytest.approx(1)
    assert bins['2026-11-18T12:00:00+00:00'] == pytest.approx(2)
    assert max(bins) == '2026-11-18T22:00:00+00:00'
    assert result['kwh'] == pytest.approx(1 + 11 * 2) and result['complete']
    assert result['points'][0] == {'time': NOW.isoformat(), 'end': '2026-11-18T12:00:00+00:00', 'w': 2000}


def test_month_and_year_forecast_use_local_days_and_months_and_report_coverage():
    rows = forecast(datetime(2026, 11, 18, 22, tzinfo=timezone.utc), 4)
    month = pv_forecast(rows, {'period': 'month', 'date': '2026-11-01', 'end': '2026-12-01'}, NOW, ZONE)
    # 22:00 UTC is still the 18th locally (23:00); the other three hours fall on the 19th.
    assert month['bins'] == [{'time': '2026-11-18', 'kwh': 2.0}, {'time': '2026-11-19', 'kwh': 6.0}]
    assert not month['complete'] and month['points'] == []
    year = pv_forecast(rows, {'period': 'year', 'date': '2026-01-01', 'end': '2027-01-01'}, NOW, ZONE)
    assert year['bins'] == [{'time': '2026-11', 'kwh': 8.0}]
    assert pv_forecast(None, {'period': 'day', 'date': '2026-11-18', 'end': '2026-11-19'}, NOW, ZONE) == \
        {'bins': [], 'points': [], 'kwh': 0, 'complete': False}


def amount(**sources):
    value = empty()
    for source, kwh in sources.items():
        value['sources'][source].update(kwh=kwh, cost_eur=0., cost_unknown_kwh=0.)
        value['kwh'] += kwh
    return value


def test_production_per_bin_by_use_and_notable_bins():
    house, export, storage = amount(pv=2, grid=1), amount(pv=3), amount(pv=1, grid=1)
    bins = lambda value, *times: [{'time': time, **value} for time in times]
    report = {'period': 'month', 'base_days': 2, 'consumers': {
        'house': {'total': house, 'bins': bins(house, '2026-11-01')},
        'export': {'total': export, 'bins': bins(export, '2026-11-02')},
        'storage': {'total': storage, 'bins': bins(storage, '2026-11-02')}}}
    result = report_values(report, ['house'])
    rows = {row['time']: row for row in result['balance']['bins']}
    assert (rows['2026-11-01']['pv_direct_kwh'], rows['2026-11-01']['pv_kwh']) == (2, 2)
    assert (rows['2026-11-02']['pv_storage_kwh'], rows['2026-11-02']['pv_export_kwh'], rows['2026-11-02']['pv_kwh']) == (1, 3, 4)
    assert result['views']['pv']['facts'] == [{'id': 'max_pv', 'time': '2026-11-02', 'unit': 'day', 'kwh': 4},
                                              {'id': 'pv_per_day', 'kwh': pytest.approx(3)}]
    assert report_values({'period': 'day', 'consumers': {}}, ['house'])['views']['pv']['facts'] == [{'id': 'no_pv'}]


def test_power_profile_carries_the_measured_pv_power():
    start = datetime(2026, 11, 17, 23, tzinfo=timezone.utc)
    samples = [{'time': (start + timedelta(minutes=minute)).isoformat(), 'solar': watts, 'grid': 0,
                'battery_charge': 0, 'battery_discharge': 0, 'house_total': watts} for minute, watts in ((0, 1000), (1, 3000))]
    assert power_profile(samples, '2026-11-18', ZONE)['points'][0]['solar'] == 2000
