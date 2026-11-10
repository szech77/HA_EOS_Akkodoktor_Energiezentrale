from datetime import datetime, timezone

from custom_components.eos_energiezentrale.energy.presentation import daily_pv_forecast


def test_forecast_splits_midnight_and_does_not_double_count_overlaps():
    now = datetime.fromisoformat("2026-11-09T22:00:00+00:00")
    slot = {"time": now.isoformat(), "end": "2026-11-10T00:00:00+00:00", "solar": 2000}
    today, tomorrow, later = daily_pv_forecast([slot, slot], now, "Europe/Berlin")
    assert (today["kwh"], today["complete"]) == (2, True)
    assert (tomorrow["kwh"], tomorrow["complete"]) == (2, False)
    assert later["kwh"] is None


def test_forecast_uses_actual_dst_day_duration():
    now = datetime.fromisoformat("2026-03-28T23:00:00+00:00")
    row = {"time": now.isoformat(), "end": "2026-03-29T22:00:00+00:00", "solar": 1000}
    day = daily_pv_forecast([row], now, "Europe/Berlin")[0]
    assert day["kwh"] == 23
    assert day["complete"]


def test_zero_is_distinct_from_missing_and_invalid_forecast():
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    rows = [{"time": now.isoformat(), "end": "2026-11-10T00:00:00+00:00", "solar": 0},
            {"time": "bad", "end": "2026-11-11T00:00:00+00:00", "solar": 123}]
    days = daily_pv_forecast(rows, now, "UTC")
    assert days[0]["kwh"] == 0 and days[0]["complete"]
    assert days[1]["kwh"] is None
