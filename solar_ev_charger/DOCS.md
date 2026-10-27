# Solar EV Charger

Keeps a Hyundai Ioniq plugged in and decides when it should charge, based on your
Powerwall's charge level and your solar production.

## The rule

The car charges while **either** of these is true:

- the Powerwall is above `powerwall_soc_threshold` (default **35%**), or
- solar production is above `solar_threshold_kw` (default **8 kW**).

It stops once **neither** is true.

A condition has to hold for `start_delay_minutes` (10) before charging starts, and
for `stop_delay_minutes` (5) before it stops, so a passing cloud doesn't switch the
car on and off. After charging stops because the Powerwall fell to 35%, it only
restarts once the Powerwall is above 35% + `powerwall_resume_margin` (5), so 40%.
Without that margin, the car would flip on and off as the Powerwall moved between
35% and 36%.

Two limits based on the car's battery apply on top of the rule. Below `car_min_soc`
(20%) the car always charges, and at `car_target_soc` (80%) it stops.

Also set the car's own AC charge limit to 80%. Bluelink only refreshes the car's
battery level every 30 minutes or so, so the add-on may notice 80% late. The car's
own limit stops it exactly on time.

## Leaving the car plugged in

A car that is always plugged in is usually full. If the add-on sends a start and the
Wall Connector shows no power, it tries once more and then waits. It won't try again
until the rule turns off and back on (usually the next day) or you unplug and plug
back in. The same applies when the car stops by itself at its charge limit. This
stops it waking a full car every 15 minutes.

When you plug in at night and the rule is off, the car may start charging by itself
anyway. The add-on stops it after `stop_delay_minutes`.

## Requirements

Install these Home Assistant integrations first:

| Device | Integration | Used for |
|---|---|---|
| Powerwall | **Tesla Powerwall** (built in) | Solar production and Powerwall charge |
| Wall Connector (Gen 3) | **Tesla Wall Connector** (built in) | Whether the car is plugged in and drawing power |
| Ioniq | **Kia Uvo / Hyundai Bluelink** (install through HACS) | Starting and stopping charging, and the car's battery level |

US Bluelink can only start and stop charging, not change how fast the car charges,
and the Wall Connector can't be controlled remotely. So the car always charges at
full speed while it's on.

## Options

| Option | Default | Meaning |
|---|---|---|
| `mode` | `auto` | `off` makes the add-on stop sending commands |
| `*_entity` | Powerwall / Wall Connector defaults | Change these to match your entity IDs (Settings → Entities) |
| `car_soc_entity` | `sensor.ioniq_5_ev_battery_level` | Your car's EV battery % sensor from Kia Uvo |
| `override_entity` | empty | Optional `input_boolean`; while it's on, the add-on leaves charging alone |
| `vehicle_device_id` | empty | Only needed if you have more than one Hyundai/Kia on the account |
| `powerwall_soc_threshold` | 35 | Charge while the Powerwall is above this % |
| `powerwall_resume_margin` | 5 | Extra % the Powerwall needs before charging restarts |
| `solar_threshold_kw` | 8 | Charge while solar production is above this |
| `start_delay_minutes` / `stop_delay_minutes` | 10 / 5 | How long a condition must hold before starting or stopping |
| `min_minutes_between_commands` | 15 | Shortest time between Bluelink commands |
| `max_commands_per_day` | 12 | Daily cap on Bluelink commands |
| `car_target_soc` / `car_min_soc` | 80 / 20 | Stop at the target; below the minimum, always charge |

## Status sensor

The add-on publishes `sensor.solar_ev_charger`. Its state explains the current
decision, and its attributes show solar power, Powerwall %, car power and how many
commands were sent today. You can add it to a dashboard. The sensor goes away when
Home Assistant restarts and comes back on the add-on's next poll.

## Things to know

- **Bluelink rate limits.** Every command wakes the car, and Hyundai may block
  accounts that send too many. Keep the command limits conservative.
- **The Powerwall rule uses stored energy.** In the evening the car charges from the
  Powerwall until it falls to 35%. Raise `powerwall_soc_threshold` if you want more
  kept back for the house overnight.
- **Full overnight charge.** Set `mode` to `off`, or turn on the override switch,
  and start charging yourself.
