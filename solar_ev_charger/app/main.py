"""Add-on entry point: poll Home Assistant, decide, and start/stop the car."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
from datetime import datetime, timedelta

from controller import START, Controller, Settings, Snapshot
from ha import HomeAssistant, SensorUnavailable

OPTIONS_PATH = "/data/options.json"
STATUS_ENTITY = "sensor.solar_ev_charger"

log = logging.getLogger("solar_ev_charger")


def load_settings(opts: dict) -> Settings:
    return Settings(
        mode=opts["mode"],
        powerwall_soc_threshold=opts["powerwall_soc_threshold"],
        powerwall_resume_margin=opts["powerwall_resume_margin"],
        solar_threshold_w=opts["solar_threshold_kw"] * 1000,
        start_delay=timedelta(minutes=opts["start_delay_minutes"]),
        stop_delay=timedelta(minutes=opts["stop_delay_minutes"]),
        min_command_interval=timedelta(minutes=opts["min_minutes_between_commands"]),
        max_commands_per_day=opts["max_commands_per_day"],
        car_target_soc=opts["car_target_soc"],
        car_min_soc=opts["car_min_soc"],
    )


def read_snapshot(ha: HomeAssistant, opts: dict) -> Snapshot:
    try:
        car_soc = ha.number(opts["car_soc_entity"])
    except (SensorUnavailable, urllib.error.HTTPError, ValueError):
        car_soc = None
    override = bool(opts.get("override_entity")) and ha.is_on(opts["override_entity"])
    return Snapshot(
        solar_w=ha.power_w(opts["solar_power_entity"]),
        car_power_w=ha.power_w(opts["charger_power_entity"]),
        powerwall_soc=ha.number(opts["powerwall_soc_entity"]),
        plugged_in=ha.is_on(opts["plugged_in_entity"]),
        car_soc=car_soc,
        override=override,
    )


def main() -> None:
    with open(OPTIONS_PATH) as f:
        opts = json.load(f)
    logging.basicConfig(
        level=logging.DEBUG if opts.get("debug") else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    ha = HomeAssistant()
    controller = Controller(load_settings(opts))
    service_data = {"device_id": opts["vehicle_device_id"]} if opts.get("vehicle_device_id") else {}
    last_want = None

    log.info("Started in %s mode", opts["mode"])
    while True:
        try:
            now = datetime.now()
            snap = read_snapshot(ha, opts)
            decision = controller.decide(now, snap)

            if decision.action:
                service = "start_charge" if decision.action == START else "stop_charge"
                log.info("%s charging: %s", decision.action.capitalize(), decision.reason)
                controller.command_sent(now, decision.action)  # count attempts; Bluelink throttles them
                ha.call_service("kia_uvo", service, service_data)
            elif decision.should_charge != last_want:
                log.info(decision.reason)
            else:
                log.debug(decision.reason)
            last_want = decision.should_charge

            ha.set_state(
                STATUS_ENTITY,
                decision.reason[:255],
                {
                    "friendly_name": "Solar EV charger",
                    "should_charge": decision.should_charge,
                    "solar_w": round(snap.solar_w),
                    "powerwall_soc": snap.powerwall_soc,
                    "car_power_w": round(snap.car_power_w),
                    "commands_today": controller.commands_today,
                    "last_action": decision.action,
                },
            )
        except SensorUnavailable as exc:
            log.warning("Sensor unavailable, skipping this cycle: %s", exc)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log.error("Home Assistant request failed: %s", exc)
        time.sleep(opts["poll_seconds"])


if __name__ == "__main__":
    main()
