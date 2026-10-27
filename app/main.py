"""Poll the Powerwall and Ioniq, decide with the controller, and send start/stop."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from controller import START, Controller, Settings, Snapshot
from powerwall import Powerwall
from ioniq import Ioniq

log = logging.getLogger("solar_ev_charger")


@dataclass
class Config:
    settings: Settings
    poll_seconds: float = 60
    car_refresh_minutes: float = 5
    pause_file: str = "/data/pause"
    status_file: str = "/data/status.json"


def load_config(env=os.environ) -> Config:
    f = lambda name, default: float(env.get(name, default))  # noqa: E731
    settings = Settings(
        mode=env.get("MODE", "auto"),
        powerwall_soc_threshold=f("POWERWALL_SOC_THRESHOLD", 35),
        powerwall_resume_margin=f("POWERWALL_RESUME_MARGIN", 5),
        solar_threshold_w=f("SOLAR_THRESHOLD_KW", 8) * 1000,
        start_delay=timedelta(minutes=f("START_DELAY_MINUTES", 10)),
        stop_delay=timedelta(minutes=f("STOP_DELAY_MINUTES", 5)),
        min_command_interval=timedelta(minutes=f("MIN_MINUTES_BETWEEN_COMMANDS", 15)),
        max_commands_per_day=int(f("MAX_COMMANDS_PER_DAY", 12)),
        car_target_soc=f("CAR_TARGET_SOC", 80),
        car_min_soc=f("CAR_MIN_SOC", 20),
    )
    return Config(
        settings=settings,
        poll_seconds=f("POLL_SECONDS", 60),
        car_refresh_minutes=f("CAR_REFRESH_MINUTES", 5),
        pause_file=env.get("PAUSE_FILE", "/data/pause"),
        status_file=env.get("STATUS_FILE", "/data/status.json"),
    )


def run(
    cfg: Config,
    powerwall,
    ioniq,
    *,
    clock=datetime.now,
    sleep=time.sleep,
    max_cycles: int | None = None,
) -> None:
    controller = Controller(cfg.settings)
    car = None  # last Bluelink reading, reused between cached refreshes
    car_read_at: datetime | None = None
    last_want = None
    cycle = 0

    log.info("Started in %s mode", cfg.settings.mode)
    while max_cycles is None or cycle < max_cycles:
        cycle += 1
        try:
            now = clock()
            pw = powerwall.live()

            if car_read_at is None or now - car_read_at >= timedelta(minutes=cfg.car_refresh_minutes):
                ioniq.refresh_cached()
                car = ioniq.read()
                car_read_at = now

            snap = Snapshot(
                solar_w=pw.solar_w,
                powerwall_soc=pw.soc,
                plugged_in=car.plugged_in,
                charging=car.charging,
                car_soc=car.soc,
                override=os.path.exists(cfg.pause_file),
            )
            decision = controller.decide(now, snap)

            if decision.action:
                log.info("%s charging: %s", decision.action.capitalize(), decision.reason)
                controller.command_sent(now, decision.action)
                if decision.action == START:
                    ioniq.start_charge()
                else:
                    ioniq.stop_charge()
                # Bluelink reports from a cached copy, so ask the car for fresh data
                # right after a command rather than waiting for the next cached refresh.
                ioniq.force_refresh()
                car_read_at = None
            elif decision.should_charge != last_want:
                log.info(decision.reason)
            else:
                log.debug(decision.reason)
            last_want = decision.should_charge

            write_status(cfg.status_file, now, decision, snap, controller)
        except Exception:  # cloud APIs fail; log and try again on the next cycle
            log.exception("Cycle failed, retrying in %s seconds", cfg.poll_seconds)
        sleep(cfg.poll_seconds)


def write_status(path, now, decision, snap, controller) -> None:
    status = {
        "time": now.isoformat(timespec="seconds"),
        "action": decision.action,
        "reason": decision.reason,
        "should_charge": decision.should_charge,
        "solar_kw": round(snap.solar_w / 1000, 2),
        "powerwall_soc": snap.powerwall_soc,
        "car_soc": snap.car_soc,
        "car_plugged_in": snap.plugged_in,
        "car_charging": snap.charging,
        "commands_today": controller.commands_today,
    }
    try:
        with open(path, "w") as f:
            json.dump(status, f, indent=2)
    except OSError as exc:
        log.warning("Could not write status file: %s", exc)


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = load_config()
    powerwall = Powerwall(os.environ["TESLEMETRY_API_KEY"], os.environ["ENERGY_SITE_ID"])
    ioniq = Ioniq(
        os.environ["BLUELINK_USERNAME"],
        os.environ["BLUELINK_PASSWORD"],
        os.environ["BLUELINK_PIN"],
        os.environ.get("BLUELINK_VEHICLE_ID") or None,
    )
    run(cfg, powerwall, ioniq)


if __name__ == "__main__":
    main()
