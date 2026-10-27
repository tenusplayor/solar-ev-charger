"""Minimal Home Assistant REST client for use inside an add-on."""

from __future__ import annotations

import json
import os
import urllib.request

UNAVAILABLE = {"unknown", "unavailable", "none", ""}
POWER_SCALE = {"w": 1.0, "kw": 1000.0, "mw": 1_000_000.0}


class SensorUnavailable(Exception):
    pass


class HomeAssistant:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 15):
        self.base_url = (base_url or os.environ.get("HA_URL", "http://supervisor/core/api")).rstrip("/")
        self.token = token or os.environ["SUPERVISOR_TOKEN"]
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None

    def state(self, entity_id: str) -> dict:
        state = self._request("GET", f"/states/{entity_id}")
        if str(state.get("state", "")).lower() in UNAVAILABLE:
            raise SensorUnavailable(entity_id)
        return state

    def number(self, entity_id: str) -> float:
        return float(self.state(entity_id)["state"])

    def power_w(self, entity_id: str) -> float:
        """Read a power sensor in watts, whatever unit the integration reports."""
        state = self.state(entity_id)
        unit = str(state.get("attributes", {}).get("unit_of_measurement", "W")).lower()
        if unit not in POWER_SCALE:
            raise ValueError(f"{entity_id} has unexpected unit {unit!r}")
        return float(state["state"]) * POWER_SCALE[unit]

    def is_on(self, entity_id: str) -> bool:
        return self.state(entity_id)["state"] == "on"

    def call_service(self, domain: str, service: str, data: dict | None = None) -> None:
        self._request("POST", f"/services/{domain}/{service}", data or {})

    def set_state(self, entity_id: str, state: str, attributes: dict) -> None:
        self._request("POST", f"/states/{entity_id}", {"state": state, "attributes": attributes})
