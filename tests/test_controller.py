from datetime import datetime, timedelta

from controller import START, STOP, Controller, Settings, Snapshot

T0 = datetime(2026, 6, 1, 10, 0)
MIN = timedelta(minutes=1)


def snap(solar=0, pw=20, car=0, plugged=True, car_soc=50, override=False):
    return Snapshot(
        solar_w=solar,
        car_power_w=car,
        powerwall_soc=pw,
        plugged_in=plugged,
        car_soc=car_soc,
        override=override,
    )


def run(ctrl, minutes, start=T0, **kw):
    """Feed one reading per minute and return the last decision."""
    decision = None
    for i in range(minutes + 1):
        decision = ctrl.decide(start + i * MIN, snap(**kw))
    return decision


def test_starts_when_solar_above_threshold():
    ctrl = Controller(Settings())
    assert run(ctrl, 5, solar=9000).action is None  # must last start_delay first
    assert run(ctrl, 10, start=T0 + 6 * MIN, solar=9000).action == START


def test_starts_when_powerwall_above_threshold():
    ctrl = Controller(Settings())
    assert run(ctrl, 10, pw=60).action == START


def test_does_nothing_when_neither_condition_holds():
    d = run(Controller(Settings()), 30, solar=7000, pw=30)
    assert d.action is None and not d.should_charge
    assert "needs > 40%" in d.reason and "needs > 8.0 kW" in d.reason


def test_stops_when_neither_condition_holds():
    ctrl = Controller(Settings())
    # Evening: solar gone and the car has drained the Powerwall to 35%.
    assert run(ctrl, 4, solar=500, pw=35, car=7000).action is None  # wait stop_delay
    assert run(ctrl, 5, start=T0 + 5 * MIN, solar=500, pw=35, car=7000).action == STOP


def test_keeps_charging_while_either_condition_holds():
    ctrl = Controller(Settings())
    assert run(ctrl, 30, solar=9000, pw=20, car=7000).action is None
    assert run(ctrl, 30, start=T0 + 31 * MIN, solar=0, pw=36, car=7000).action is None


def test_powerwall_needs_margin_to_restart():
    ctrl = Controller(Settings(powerwall_soc_threshold=35, powerwall_resume_margin=5))
    assert run(ctrl, 15, pw=38).action is None  # stopped at 35%, not back above 40%
    assert run(ctrl, 15, start=T0 + 16 * MIN, pw=41).action == START


def test_brief_cloud_does_not_stop_charging():
    ctrl = Controller(Settings())
    for i in range(30):
        solar = 2000 if 10 <= i < 13 else 9000  # 3-minute dip, stop_delay is 5
        d = ctrl.decide(T0 + i * MIN, snap(solar=solar, car=7000))
        assert d.action is None


def test_full_car_is_not_woken_repeatedly():
    ctrl = Controller(Settings(min_command_interval=timedelta(minutes=15)))
    sent = 0
    for i in range(8 * 60):  # sunny all day, car never draws power
        d = ctrl.decide(T0 + i * MIN, snap(solar=9000))
        if d.action:
            ctrl.command_sent(T0 + i * MIN, d.action)
            sent += 1
    assert sent == 2
    assert "probably full" in d.reason


def test_does_not_restart_after_car_stops_itself():
    ctrl = Controller(Settings())
    run(ctrl, 20, solar=9000, car=7000)  # charging
    d = run(ctrl, 30, start=T0 + 21 * MIN, solar=9000, car=0)  # car hit its own limit
    assert d.action is None and "probably full" in d.reason


def test_new_attempt_after_conditions_reset():
    ctrl = Controller(Settings())
    run(ctrl, 20, solar=9000, car=7000)
    run(ctrl, 600, start=T0 + 21 * MIN, solar=0, pw=20)  # overnight
    tomorrow = T0 + timedelta(days=1)
    assert run(ctrl, 10, start=tomorrow, solar=9000).action == START


def test_replug_resets_attempts():
    ctrl = Controller(Settings())
    run(ctrl, 20, solar=9000, car=7000)
    run(ctrl, 2, start=T0 + 21 * MIN, plugged=False)
    assert run(ctrl, 10, start=T0 + 24 * MIN, solar=9000).action == START


def test_target_and_min_soc():
    ctrl = Controller(Settings(car_target_soc=80, car_min_soc=20))
    assert run(ctrl, 10, solar=9000, car=7000, car_soc=80).action == STOP
    ctrl = Controller(Settings(car_min_soc=20))
    assert run(ctrl, 10, solar=0, pw=10, car_soc=15).action == START


def test_unknown_car_soc_still_works():
    assert run(Controller(Settings()), 10, solar=9000, car_soc=None).action == START


def test_override_off_and_unplugged_do_nothing():
    assert run(Controller(Settings()), 10, solar=9000, override=True).reason == "manual override on"
    assert run(Controller(Settings(mode="off")), 10, solar=9000).reason == "mode is off"
    assert run(Controller(Settings()), 10, solar=9000, plugged=False).reason == "not plugged in"


def test_rate_limited_between_commands():
    ctrl = Controller(Settings(min_command_interval=timedelta(minutes=15)))
    assert run(ctrl, 10, solar=9000, car=7000, pw=10).action is None
    run(ctrl, 10, start=T0 + 11 * MIN, solar=0, pw=10, car=7000)
    ctrl.command_sent(T0 + 21 * MIN, STOP)
    d = ctrl.decide(T0 + 22 * MIN, snap(solar=0, pw=10, car=7000))
    assert d.action is None and "rate limited" in d.reason
    assert ctrl.decide(T0 + 36 * MIN, snap(solar=0, pw=10, car=7000)).action == STOP


def test_daily_command_cap_resets_next_day():
    ctrl = Controller(Settings(max_commands_per_day=1, min_command_interval=timedelta(0)))
    run(ctrl, 10, solar=0, pw=10, car=7000)
    ctrl.command_sent(T0 + 10 * MIN, STOP)
    assert "rate limited" in ctrl.decide(T0 + 11 * MIN, snap(pw=10, car=7000)).reason
    tomorrow = T0 + timedelta(days=1)
    assert run(ctrl, 10, start=tomorrow, pw=10, car=7000).action == STOP
