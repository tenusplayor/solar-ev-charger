"""Solar-surplus charging decisions, independent of Home Assistant.

The car can only be started and stopped (US Bluelink has no current control and a
Tesla Wall Connector is not remotely controllable), so the controller decides *when*
to run the charger at its fixed rate:

* surplus  = solar - (house load - car load)    power the car could take from solar
* shortfall = car load - surplus                power the car is pulling from the
                                                Powerwall or the grid while charging

Charging starts once the average surplus over ``start_delay`` covers the car's
charging power (minus the tolerated shortfall), and stops once the average shortfall
over ``stop_delay`` exceeds that tolerance. Commands are rate limited because every
Bluelink command wakes the car and Hyundai throttles accounts that send too many.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

START = "start"
STOP = "stop"

# Wall Connector power above this means the car is actually drawing current.
CHARGING_THRESHOLD_W = 500


@dataclass
class Settings:
    mode: str = "solar"  # "solar" or "off"
    charge_power_w: float = 7200.0
    allowed_shortfall_w: float = 500.0
    start_delay: timedelta = timedelta(minutes=10)
    stop_delay: timedelta = timedelta(minutes=5)
    min_command_interval: timedelta = timedelta(minutes=15)
    max_commands_per_day: int = 12
    powerwall_min_soc: float = 90.0
    car_target_soc: float = 80.0
    car_min_soc: float = 20.0


@dataclass
class Snapshot:
    """One reading of the home and car, all power values in watts."""

    solar_w: float
    load_w: float  # whole-home load as reported by the Powerwall, car included
    car_power_w: float  # from the Wall Connector
    powerwall_soc: float
    plugged_in: bool
    car_soc: float | None = None  # Bluelink data is cached and may be missing
    override: bool = False  # user has taken manual control

    @property
    def surplus_w(self) -> float:
        return self.solar_w - (self.load_w - self.car_power_w)

    @property
    def charging(self) -> bool:
        return self.car_power_w > CHARGING_THRESHOLD_W


@dataclass
class Decision:
    action: str | None  # START, STOP or None
    reason: str
    surplus_w: float = 0.0
    avg_surplus_w: float | None = None
    avg_shortfall_w: float | None = None


@dataclass
class Controller:
    settings: Settings
    _samples: deque = field(default_factory=deque)  # (time, surplus_w, car_power_w)
    _charging_since: datetime | None = None
    _last_command_at: datetime | None = None
    _commands_day: date | None = None
    _commands_today: int = 0
    learned_charge_power_w: float | None = None

    @property
    def charge_power_w(self) -> float:
        return self.learned_charge_power_w or self.settings.charge_power_w

    @property
    def commands_today(self) -> int:
        return self._commands_today

    def decide(self, now: datetime, snap: Snapshot) -> Decision:
        self._record(now, snap)
        decision = self._decide(now, snap)
        if decision.action and not self._may_send(now):
            decision = Decision(
                None,
                f"wanted to {decision.action} ({decision.reason}) but rate limited",
                decision.surplus_w,
                decision.avg_surplus_w,
                decision.avg_shortfall_w,
            )
        return decision

    def command_sent(self, now: datetime) -> None:
        self._roll_day(now)
        self._last_command_at = now
        self._commands_today += 1

    def _decide(self, now: datetime, snap: Snapshot) -> Decision:
        s = self.settings
        surplus = snap.surplus_w

        def result(action, reason, **kw):
            return Decision(action, reason, surplus, **kw)

        if s.mode == "off":
            return result(None, "mode is off")
        if snap.override:
            return result(None, "manual override on")
        if not snap.plugged_in:
            return result(None, "not plugged in")

        car_soc = snap.car_soc
        below_min = car_soc is not None and car_soc < s.car_min_soc
        at_target = car_soc is not None and car_soc >= s.car_target_soc

        if snap.charging:
            if at_target:
                return result(STOP, f"car reached {car_soc:.0f}% target")
            if below_min:
                return result(None, f"car below {s.car_min_soc:.0f}%, charging from any source")
            shortfall = self._average(now, s.stop_delay, lambda su, car: car - su, charging_only=True)
            if shortfall is None:
                return result(None, "charging, collecting data")
            if shortfall > s.allowed_shortfall_w:
                return result(
                    STOP,
                    f"pulling {shortfall:.0f} W from Powerwall/grid",
                    avg_shortfall_w=shortfall,
                )
            return result(None, "charging on solar", avg_shortfall_w=shortfall)

        if at_target:
            return result(None, f"car at {car_soc:.0f}%, target reached")
        if below_min:
            return result(START, f"car below {s.car_min_soc:.0f}% minimum")
        if snap.powerwall_soc < s.powerwall_min_soc:
            return result(
                None,
                f"Powerwall at {snap.powerwall_soc:.0f}%, filling it to {s.powerwall_min_soc:.0f}% first",
            )
        avg = self._average(now, s.start_delay, lambda su, car: su)
        if avg is None:
            return result(None, "waiting, collecting data")
        needed = self.charge_power_w - s.allowed_shortfall_w
        if avg >= needed:
            return result(START, f"solar surplus {avg:.0f} W", avg_surplus_w=avg)
        return result(None, f"surplus {avg:.0f} W, need {needed:.0f} W", avg_surplus_w=avg)

    def _record(self, now: datetime, snap: Snapshot) -> None:
        if snap.charging:
            if self._charging_since is None:
                self._charging_since = now
            elif now - self._charging_since > timedelta(minutes=5):
                # Learn the real charging rate once the car has ramped up.
                prev = self.learned_charge_power_w
                self.learned_charge_power_w = (
                    snap.car_power_w if prev is None else 0.9 * prev + 0.1 * snap.car_power_w
                )
        else:
            self._charging_since = None

        self._samples.append((now, snap.surplus_w, snap.car_power_w))
        horizon = max(self.settings.start_delay, self.settings.stop_delay)
        while self._samples and now - self._samples[0][0] > horizon:
            self._samples.popleft()

    def _average(self, now, window, value, charging_only=False):
        """Average over ``window``, or None until the window is covered by data."""
        since = now - window
        if charging_only and (self._charging_since is None or self._charging_since > since):
            return None
        points = [(t, su, car) for t, su, car in self._samples if t >= since]
        if not points or points[0][0] - since > window * 0.2:
            return None
        return sum(value(su, car) for _, su, car in points) / len(points)

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
