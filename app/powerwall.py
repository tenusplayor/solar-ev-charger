"""Read Powerwall solar production and battery charge through Teslemetry's cloud API."""

from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass

BASE_URL = "https://api.teslemetry.com"


@dataclass
class PowerwallState:
    solar_w: float
    soc: float


class Powerwall:
    def __init__(self, api_key: str, energy_site_id: str, timeout: float = 15):
        self.api_key = api_key
        self.energy_site_id = energy_site_id
        self.timeout = timeout

    def _get(self, path: str):
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            # Teslemetry rejects urllib's default User-Agent with 403.
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": "solar-ev-charger/0.1"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)["response"]

    def live(self) -> PowerwallState:
        data = self._get(f"/api/1/energy_sites/{self.energy_site_id}/live_status")
        return PowerwallState(
            solar_w=float(data.get("solar_power") or 0),
            soc=float(data.get("percentage_charged") or 0),
        )


def list_energy_sites(api_key: str) -> list[dict]:
    """Return the energy sites on the account, so you can find your energy_site_id."""
    products = Powerwall(api_key, "")._get("/api/1/products")
    return [p for p in products if "energy_site_id" in p]


if __name__ == "__main__":
    # Usage: TESLEMETRY_API_KEY=... python powerwall.py
    import os

    key = os.environ.get("TESLEMETRY_API_KEY")
    if not key:
        sys.exit("Set TESLEMETRY_API_KEY first")
    for site in list_energy_sites(key):
        print(f"{site['energy_site_id']}  {site.get('site_name', '')}")
