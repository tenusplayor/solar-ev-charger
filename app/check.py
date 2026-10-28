"""Read-only check: confirm Teslemetry and Bluelink work with the settings in .env.

Run from the project folder:  python3 app/check.py
It never starts or stops charging.
"""

import os
import sys
from pathlib import Path

from ioniq import Ioniq
from powerwall import Powerwall

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path) -> None:
    """Read KEY=VALUE lines from .env into os.environ. Empty shell variables don't count as set."""
    if not path.exists():
        # Inside Docker, docker compose passes the settings in as environment variables.
        print(f"No .env file at {path}; using environment variables")
        return
    print(f"Reading settings from {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if not os.environ.get(key.strip()):
            os.environ[key.strip()] = value


def require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"{name} is empty in .env")
    return value


def main() -> None:
    load_env(ENV_FILE)

    print("Powerwall (Teslemetry)...")
    pw = Powerwall(require("TESLEMETRY_API_KEY"), require("ENERGY_SITE_ID")).live()
    print(f"  solar: {pw.solar_w:.0f} W   battery: {pw.soc:.0f}%")

    print("Ioniq (Bluelink)...")
    car = Ioniq(
        require("BLUELINK_USERNAME"),
        require("BLUELINK_PASSWORD"),
        require("BLUELINK_PIN"),
        os.environ.get("BLUELINK_VEHICLE_ID") or None,
    )
    car.refresh_cached()
    state = car.read()
    print(f"  battery: {state.soc}%   plugged in: {state.plugged_in}   charging: {state.charging}")

    print("OK. Both services responded. Nothing was started or stopped.")


if __name__ == "__main__":
    main()
