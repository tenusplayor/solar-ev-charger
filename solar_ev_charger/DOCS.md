# Solar EV Charger

Charges a Hyundai Ioniq only when your solar panels make more power than the house
is using, so the car isn't charged from the Powerwall or the grid.

## How it works

Every `poll_seconds` the add-on reads your Powerwall and Wall Connector sensors and
works out:

- **Surplus** = solar − (house load − car load): the power the car could take from solar.
- **Shortfall** (while charging) = car load − surplus: the power the car is pulling
  from the Powerwall or the grid.

It **starts** charging through Bluelink when:

1. the car is plugged in and below `car_target_soc`, and
2. the Powerwall is at least `powerwall_min_soc`, so the house battery fills first, and
3. the average surplus over `start_delay_minutes` covers the car's charging power,
   minus `allowed_shortfall_w`.

It **stops** charging when the average shortfall over `stop_delay_minutes` is more
than `allowed_shortfall_w`, or when the car reaches `car_target_soc`.

If the car is below `car_min_soc` it charges from any source, so you're never left
with an empty car.

The add-on learns how much power the car actually draws from the Wall Connector, so
`charge_power_w` is only the starting guess.

## Requirements

Install these Home Assistant integrations first:

| Device | Integration | Notes |
|---|---|---|
| Powerwall | **Tesla Powerwall** (built in) | Connects to the Gateway on your home network |
| Wall Connector (Gen 3) | **Tesla Wall Connector** (built in) | Read-only, used to measure car power and plug state |
| Ioniq | **Kia Uvo / Hyundai Bluelink** (install through HACS) | Provides the `kia_uvo.start_charge` / `stop_charge` services |

## Important: the car charges at one fixed rate

A US Ioniq can't be told to charge more slowly over Bluelink, and a Tesla Wall
Connector can't be controlled remotely. The car always charges at full speed, which
on a 48 A Wall Connector is about 11 kW. That is more spare solar than most homes
ever have, so the add-on would rarely start.

There are two ways to bring the charging rate down to match your solar:

- **Lower the Wall Connector's maximum current** in the Tesla One app's
  commissioning settings (for example 24 A ≈ 5.8 kW or 16 A ≈ 3.8 kW). This also
  slows any charging you do overnight.
- **Lower the car's AC charging current** in the Ioniq's EV charging settings menu,
  if your model offers it.

Then set `charge_power_w` to roughly the new rate. A higher `allowed_shortfall_w`
lets charging start on partly sunny days, with the Powerwall covering the gap.

## Options

| Option | Default | Meaning |
|---|---|---|
| `mode` | `solar` | `off` makes the add-on stop sending commands |
| `*_entity` | Powerwall / Wall Connector defaults | Change these to match your entity IDs (Settings → Entities) |
| `car_soc_entity` | `sensor.ioniq_5_ev_battery_level` | Your car's EV battery % sensor from Kia Uvo |
| `override_entity` | empty | Optional `input_boolean`; while it's on, the add-on leaves charging alone |
| `vehicle_device_id` | empty | Only needed if you have more than one Hyundai/Kia on the account |
| `charge_power_w` | 7200 | Starting guess for how much power the car draws while charging |
| `allowed_shortfall_w` | 500 | How much Powerwall/grid power charging may use |
| `start_delay_minutes` / `stop_delay_minutes` | 10 / 5 | How long to average before starting or stopping |
| `min_minutes_between_commands` | 15 | Shortest time between Bluelink commands |
| `max_commands_per_day` | 12 | Daily cap on Bluelink commands |
| `powerwall_min_soc` | 90 | Fill the Powerwall to this level before charging the car (0 = car first) |
| `car_target_soc` / `car_min_soc` | 80 / 20 | Stop charging at the target; below the minimum, charge from any source |

## Status sensor

The add-on publishes `sensor.solar_ev_charger`. Its state explains the current
decision, and its attributes show the surplus, the shortfall, the learned charging
power and how many commands were sent today. You can add it to a dashboard.
This sensor goes away when Home Assistant restarts and comes back on the add-on's
next poll.

## Things to know

- **Bluelink rate limits.** Every command wakes the car, and Hyundai may block
  accounts that send too many. Keep the command limits conservative.
- **Plugging in at night.** The Ioniq starts charging as soon as it's plugged in.
  With no solar, the add-on stops it after `stop_delay_minutes` unless the car is
  below `car_min_soc`. Turn the add-on to `off`, or use the override switch, when
  you need a full charge overnight.
- **Check how your house is metered.** When the car charges, the Powerwall's
  *Load power* should rise by the same amount. If it doesn't, the Wall Connector is
  outside the Gateway's meters and the surplus calculation will be wrong.
