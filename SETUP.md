# Cloud setup

The service runs in Docker on a small Linux server and talks to:
- **Teslemetry** for Powerwall solar production and battery %
- **Hyundai Bluelink** for the Ioniq's plugged-in, charging and battery state, and for start/stop

It doesn't need anything at home.

## 1. Teslemetry

1. Sign up at [teslemetry.com](https://teslemetry.com) and link your Tesla account, the
   one your Powerwall is on.
2. Accept the Tesla Fleet API permissions for the energy site. Teslemetry walks you
   through this.
3. Create an API key in the Teslemetry dashboard and keep it for `.env`.

## 2. Find your energy site ID

```sh
TESLEMETRY_API_KEY=your_key python3 app/powerwall.py
```

It prints one line per energy site. Copy the ID into `ENERGY_SITE_ID`.

## 3. Server

Any Linux VPS with Docker works: about 1 GB RAM, around $5/month. Install Docker
(`curl -fsSL https://get.docker.com | sh`), then copy this folder onto it.

## 4. Configure and start

```sh
cp .env.example .env     # fill in the keys and Bluelink login
docker compose up -d --build
docker compose logs -f   # watch the decisions
```

`data/status.json` holds the latest decision and readings.

## 5. Pause or resume

- **Pause:** `touch data/pause`. The service stops sending commands and keeps watching.
- **Resume:** `rm data/pause`.

## Things to check first

- **Bluelink one-time codes.** Hyundai may email a verification code the first time you
  log in from a new location, such as a server. The service then stops with an
  `AuthenticationOTPRequired` error in the logs. Log in once from the server's
  environment to handle that before relying on it.
- **Car data lag.** Bluelink's view of the car is cached and can lag by 30 minutes or more.
  The service asks the car for fresh data after each command, but it still reacts more
  slowly than the old Home Assistant version would have.
- **Cost.** Teslemetry starts at about $2.50/month base, plus any per-vehicle fee. Check
  the [pricing page](https://teslemetry.com/pricing) because numbers change.
