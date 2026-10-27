from datetime import datetime, timedelta

from controller import START, STOP, Controller, Settings, Snapshot

T0 = datetime(2026, 6, 1, 10, 0)
MIN = timedelta(minutes=1)


def snap(solar=9000, house=1000, car=0, pw=100, plugged=True, car_soc=50, override=False):
    """Build a snapshot from house load excluding the car, like the Powerwall sees it."""
    return Snapshot(
        solar_w=solar,
        load_w=house + car,
        car_power_w=car,
        powerwall_soc=pw,
        plugged_in=plugged,
        car_soc=car_soc,
        override=override,
    )


def run(ctrl, minutes, start=T0, **kw):
    """Feed one sample per minute and return the last decision."""
    decision = None
    for i in range(minutes + 1):
        decision = ctrl.decide(start + i * MIN, snap(**kw))
    return decision


def test_surplus_excludes_car_load():
    s = snap(solar=9000, house=1000, car=7000)
    assert s.surplus_w == 8000
    assert s.charging


def test_starts_after_sustained_surplus():
    ctrl = Controller(Settings())
    assert run(ctrl, 5).action is None  # not enough history yet
    assert run(ctrl, 10).action == START


def test_does_not_start_when_surplus_too_small():
    ctrl = Controller(Settings(charge_power_w=7200, allowed_shortfall_w=500))
    d = run(ctrl, 15, solar=7000, house=1000)  # 6000 W surplus < 6700 W needed
    assert d.action is None
    assert "need 6700" in d.reason


def test_brief_cloud_does_not_block_start():
    ctrl = Controller(Settings())
    for i in range(11):
        solar = 3000 if i == 5 else 9500
        d = ctrl.decide(T0 + i * MIN, snap(solar=solar))
    assert d.action == START


def test_waits_for_powerwall_to_fill():
    ctrl = Controller(Settings(powerwall_min_soc=90))
    d = run(ctrl, 15, pw=70)
    assert d.action is None
    assert "Powerwall at 70%" in d.reason


def test_stops_when_pulling_from_battery():
    ctrl = Controller(Settings())
    # Charging at 7 kW but only 4 kW of solar surplus: 3 kW comes from the Powerwall.
    d = run(ctrl, 10, solar=5000, house=1000, car=7000)
    assert d.action == STOP
    assert "3000 W" in d.reason


def test_keeps_charging_on_small_shortfall():
    ctrl = Controller(Settings(allowed_shortfall_w=500))
    d = run(ctrl, 10, solar=7700, house=1000, car=7000)  # 300 W shortfall
    assert d.action is None
    assert d.reason == "charging on solar"


def test_stops_at_target_soc():
    ctrl = Controller(Settings(car_target_soc=80))
    d = ctrl.decide(T0, snap(car=7000, car_soc=80))
    assert d.action == STOP


def test_charges_from_any_source_below_min_soc():
    ctrl = Controller(Settings(car_min_soc=20))
    assert ctrl.decide(T0, snap(solar=0, car_soc=10)).action == START
    d = run(ctrl, 10, start=T0 + 20 * MIN, solar=0, car=7000, car_soc=15)
    assert d.action is None


def test_unknown_car_soc_still_works():
    ctrl = Controller(Settings())
    assert run(ctrl, 10, car_soc=None).action == START


def test_override_and_off_and_unplugged_do_nothing():
    assert run(Controller(Settings()), 10, override=True).reason == "manual override on"
    assert run(Controller(Settings(mode="off")), 10).reason == "mode is off"
    assert run(Controller(Settings()), 10, plugged=False).reason == "not plugged in"


def test_rate_limits_between_commands():
    ctrl = Controller(Settings(min_command_interval=timedelta(minutes=15)))
    assert run(ctrl, 10).action == START
    ctrl.command_sent(T0 + 10 * MIN)
    # Car never started drawing; a retry must wait out the interval.
    d = ctrl.decide(T0 + 11 * MIN, snap())
    assert d.action is None and "rate limited" in d.reason
    assert run(ctrl, 13, start=T0 + 12 * MIN).action == START  # minute 25


def test_daily_command_cap_resets_next_day():
    ctrl = Controller(Settings(max_commands_per_day=1, min_command_interval=timedelta(0)))
    run(ctrl, 10)
    ctrl.command_sent(T0 + 10 * MIN)
    assert "rate limited" in ctrl.decide(T0 + 11 * MIN, snap()).reason
    tomorrow = T0 + timedelta(days=1)
    assert run(ctrl, 10, start=tomorrow).action == START


def test_learns_actual_charge_power():
    ctrl = Controller(Settings(charge_power_w=7200))
    run(ctrl, 60, solar=12000, car=10900)
    assert 10000 < ctrl.charge_power_w <= 10900
