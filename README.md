# Solar EV Charger

Charges a Hyundai Ioniq when the Powerwall is above 35% or solar production is above
8 kW, and stops when neither holds. Runs in the cloud.

- `app/controller.py`: the charging rule, rate limits and "car is full" detection
- `app/powerwall.py`: Powerwall solar and battery via Teslemetry
- `app/ioniq.py`: Ioniq status and start/stop via Bluelink
- `app/main.py`: the polling loop

See [SETUP.md](SETUP.md) to deploy.

## Development

```sh
pip install -r requirements.txt pytest
python3 -m pytest
```

The tests use fake Powerwall and car clients. They don't call Teslemetry or Hyundai.
