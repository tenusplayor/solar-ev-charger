"""Charging decisions, independent of any data source or API.

The Ioniq can only be started and stopped through Bluelink (US Bluelink has no current
control). The car should charge while

    Powerwall charge > powerwall_soc_threshold   OR   solar production > solar_threshold_w

and stop once neither is true. Each condition has to hold for ``start_delay`` /
``stop_delay`` before anything is sent, so a passing cloud doesn't toggle the car.

The car stays plugged in, so it is often full. After a start, or once the car has been
seen charging, no further start is sent until the rule turns off again or the car is
unplugged; otherwise a full car would be woken up every few minutes. Commands are also
rate limited because Hyundai throttles accounts that send too many.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

START = "start"
STOP = "stop"

# Start attempts per "should charge" period before assuming the car is full.
MAX_START_ATTEMPTS = 2


@dataclass
class Settings:
    mode: str = "auto"  # "auto" or "off"
    powerwall_soc_threshold: float = 35.0
    powerwall_resume_margin: float = 5.0
    solar_threshold_w: float = 8000.0
    start_delay: timedelta = timedelta(minutes=10)
    stop_delay: timedelta = timedelta(minutes=5)
    min_command_interval: timedelta = timedelta(minutes=15)
    max_commands_per_day: int = 12
    car_target_soc: float = 80.0
    car_min_soc: float = 20.0


@dataclass
class Snapshot:
    solar_w: float
    powerwall_soc: float
    plugged_in: bool
    charging: bool  # as reported by Bluelink, which is cached and can lag by ~30 minutes
    car_soc: float | None = None
    override: bool = False  # user has taken manual control


@dataclass
class Decision:
    action: str | None  # START, STOP or None
    reason: str
    should_charge: bool = False


class Controller:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._want: bool | None = None
        self._want_since: datetime | None = None
        self._start_attempts = 0
        self._last_command_at: datetime | None = None
        self._commands_day: date | None = None
        self._commands_today = 0

    @property
    def commands_today(self) -> int:
        return self._commands_today

    def decide(self, now: datetime, snap: Snapshot) -> Decision:
        decision = self._decide(now, snap)
        if decision.action and not self._may_send(now):
            decision = Decision(
                None,
                f"wanted to {decision.action} ({decision.reason}) but rate limited",
                decision.should_charge,
            )
        return decision

    def command_sent(self, now: datetime, action: str) -> None:
        self._roll_day(now)
        self._last_command_at = now
        self._commands_today += 1
        if action == START:
            self._start_attempts += 1

    def should_charge(self, snap: Snapshot) -> tuple[bool, str]:
        s = self.settings
        if snap.car_soc is not None:
            if snap.car_soc >= s.car_target_soc:
                return False, f"car at {snap.car_soc:.0f}%, target reached"
            if snap.car_soc < s.car_min_soc:
                return True, f"car below {s.car_min_soc:.0f}% minimum"
        # Once charging has stopped, require a little headroom before draining the
        # Powerwall again, so it doesn't flip on and off around the threshold.
        pw_threshold = s.powerwall_soc_threshold
        if not snap.charging:
            pw_threshold += s.powerwall_resume_margin
        if snap.powerwall_soc > pw_threshold:
            return True, f"Powerwall at {snap.powerwall_soc:.0f}% (> {pw_threshold:.0f}%)"
        if snap.solar_w > s.solar_threshold_w:
            return True, f"solar at {snap.solar_w / 1000:.1f} kW"
        return False, (
            f"Powerwall at {snap.powerwall_soc:.0f}% (needs > {pw_threshold:.0f}%) and "
            f"solar at {snap.solar_w / 1000:.1f} kW (needs > {s.solar_threshold_w / 1000:.1f} kW)"
        )

    def _decide(self, now: datetime, snap: Snapshot) -> Decision:
        s = self.settings
        if s.mode == "off":
            return Decision(None, "mode is off")
        if snap.override:
            return Decision(None, "manual override on")
        if not snap.plugged_in:
            self._reset_want(None, now)
            return Decision(None, "not plugged in")

        want, why = self.should_charge(snap)
        if want != self._want:
            self._reset_want(want, now)
        held = now - self._want_since

        if snap.charging:
            # The car took the start (or was started by hand); don't restart it once
            # it stops on its own at its charge limit.
            self._start_attempts = MAX_START_ATTEMPTS
            if want:
                return Decision(None, f"charging: {why}", want)
            if held >= s.stop_delay:
                return Decision(STOP, why, want)
            return Decision(None, f"charging, will stop if this lasts: {why}", want)

        if not want:
            return Decision(None, f"not charging: {why}", want)
        if self._start_attempts >= MAX_START_ATTEMPTS:
            return Decision(None, f"car not drawing power, probably full ({why})", want)
        if held >= s.start_delay:
            return Decision(START, why, want)
        return Decision(None, f"will start if this lasts: {why}", want)

    def _reset_want(self, want: bool | None, now: datetime) -> None:
        self._want = want
        self._want_since = now
        self._start_attempts = 0

    def _roll_day(self, now: datetime) -> None:
        if self._commands_day != now.date():
            self._commands_day = now.date()
            self._commands_today = 0

    def _may_send(self, now: datetime) -> bool:
        self._roll_day(now)
        if self._commands_today >= self.settings.max_commands_per_day:
            return False
        last = self._last_command_at
        return last is None or now - last >= self.settings.min_command_interval
