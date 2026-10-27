from datetime import datetime, timedelta
from types import SimpleNamespace

import main
from controller import START, STOP

T0 = datetime(2026, 6, 1, 10, 0)


class FakePowerwall:
    def __init__(self, solar_w=9000, soc=20):
        self.solar_w, self.soc = solar_w, soc
        self.fail_next = False

    def live(self):
        if self.fail_next:
            self.fail_next = False
            raise OSError("network down")
        return SimpleNamespace(solar_w=self.solar_w, soc=self.soc)


class FakeIoniq:
    def __init__(self, plugged=True, charging=False, soc=50):
        self.plugged, self.charging, self.soc = plugged, charging, soc
        self.calls = []

    def refresh_cached(self):
        self.calls.append("refresh_cached")

    def read(self):
        return SimpleNamespace(plugged_in=self.plugged, charging=self.charging, soc=self.soc)

    def start_charge(self):
        self.calls.append("start")
        self.charging = True

    def stop_charge(self):
        self.calls.append("stop")
        self.charging = False

    def force_refresh(self):
        self.calls.append("force_refresh")


def config(tmp_path, **env):
    base = {"PAUSE_FILE": str(tmp_path / "pause"), "STATUS_FILE": str(tmp_path / "status.json"),
            "POLL_SECONDS": "60"}
    return main.load_config({**base, **env})


def simulate(tmp_path, pw, ioniq, minutes, **env):
    now = [T0]
    sleeps = []
    main.run(
        config(tmp_path, **env), pw, ioniq,
        clock=lambda: now[0],
        sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + timedelta(minutes=1))),
        max_cycles=minutes,
    )
    return now[0]


def test_starts_on_solar_then_sends_fresh_refresh(tmp_path):
    ioniq = FakeIoniq()
    simulate(tmp_path, FakePowerwall(solar_w=9000), ioniq, 15)
    assert "start" in ioniq.calls
    assert ioniq.calls[ioniq.calls.index("start") + 1] == "force_refresh"


def test_stops_when_conditions_end(tmp_path):
    ioniq = FakeIoniq(charging=True)
    pw = FakePowerwall(solar_w=0, soc=30)
    simulate(tmp_path, pw, ioniq, 15)
    assert ioniq.calls.count("stop") == 1


def test_does_nothing_when_unplugged(tmp_path):
    ioniq = FakeIoniq(plugged=False)
    simulate(tmp_path, FakePowerwall(solar_w=9000), ioniq, 15)
    assert not any(c in ("start", "stop") for c in ioniq.calls)


def test_pause_file_blocks_commands(tmp_path):
    (tmp_path / "pause").write_text("")
    ioniq = FakeIoniq()
    simulate(tmp_path, FakePowerwall(solar_w=9000), ioniq, 15)
    assert "start" not in ioniq.calls


def test_survives_failed_cycle_and_keeps_running(tmp_path):
    pw = FakePowerwall(solar_w=9000)
    pw.fail_next = True
    ioniq = FakeIoniq()
    simulate(tmp_path, pw, ioniq, 15)
    assert "start" in ioniq.calls


def test_car_is_read_from_bluelink_cache_every_few_minutes(tmp_path):
    ioniq = FakeIoniq()
    simulate(tmp_path, FakePowerwall(solar_w=0, soc=10), ioniq, 12, CAR_REFRESH_MINUTES="5")
    assert ioniq.calls.count("refresh_cached") == 3


def test_status_file_written(tmp_path):
    simulate(tmp_path, FakePowerwall(solar_w=9000), FakeIoniq(), 3)
    import json
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["solar_kw"] == 9.0
    assert status["car_plugged_in"] is True
