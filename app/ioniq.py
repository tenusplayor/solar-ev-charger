"""Ioniq status and charge start/stop through Hyundai Bluelink (hyundai-kia-connect-api)."""

from __future__ import annotations

from dataclasses import dataclass

import hyundai_kia_connect_api as hk
from hyundai_kia_connect_api import const

# Numeric codes the library expects: region 3 is USA, brand 2 is Hyundai.
REGION_USA = next(k for k, v in const.REGIONS.items() if v == const.REGION_USA)
BRAND_HYUNDAI = next(k for k, v in const.BRANDS.items() if v == const.BRAND_HYUNDAI)


@dataclass
class IoniqState:
    soc: float | None
    plugged_in: bool
    charging: bool


class Ioniq:
    def __init__(self, username: str, password: str, pin: str, vehicle_id: str | None = None):
        self.vm = hk.VehicleManager(
            region=REGION_USA,
            brand=BRAND_HYUNDAI,
            username=username,
            password=password,
            pin=pin,
        )
        self.vm.check_and_refresh_token()
        self.vehicle_id = vehicle_id or next(iter(self.vm.vehicles))

    def refresh_cached(self) -> None:
        """Pull the latest cached data from Hyundai's servers. Doesn't wake the car."""
        self.vm.check_and_refresh_token()
        self.vm.update_vehicle_with_cached_state(self.vehicle_id)

    def force_refresh(self) -> None:
        """Ask the car for fresh data. Wakes the car, so use sparingly."""
        self.vm.force_refresh_vehicle_state(self.vehicle_id)

    def read(self) -> IoniqState:
        v = self.vm.get_vehicle(self.vehicle_id)
        return IoniqState(
            soc=v.ev_battery_percentage,
            plugged_in=bool(v.ev_battery_is_plugged_in),
            charging=bool(v.ev_battery_is_charging),
        )

    def start_charge(self) -> None:
        self.vm.start_charge(self.vehicle_id)

    def stop_charge(self) -> None:
        self.vm.stop_charge(self.vehicle_id)
