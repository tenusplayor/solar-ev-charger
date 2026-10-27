# Setup guide

You need **Home Assistant OS** (or a Supervised install). Add-ons aren't available on
Home Assistant Container or Core installs. Check under **Settings → About**.

## 1. Car (Ioniq)

1. **Set the AC charge limit to 80%.** Use the car's EV settings screen (charging
   settings / target battery level) or the Hyundai app. The car then stops at 80% on
   its own. The add-on also stops at 80% as a backup, but it sees the battery level
   late.
2. **Turn off scheduled charging** (and any off-peak-only charging) in the car or the
   Hyundai app. Otherwise the car may ignore start commands outside its schedule.
3. Make sure Bluelink is active and that you know your Hyundai account email,
   password and PIN.

## 2. Home Assistant integrations

### Powerwall

**Powerwall 2:** go to **Settings → Devices & services → Add integration → Tesla
Powerwall**.

- **IP address:** the Gateway's IP address, from your router (often detected automatically).
- **Password:** the last 5 characters of the password printed inside the Backup
  Gateway. If there isn't one, use the last 5 characters of the Gateway serial
  number from the Tesla app.

**Powerwall 3:** Home Assistant's Powerwall integration only partly supports
Powerwall 3. If solar power or charge % are missing, use the **Tesla Fleet**
integration (built in, requires a Tesla developer account) or **Teslemetry** (a paid
service with easier setup) instead, and point the add-on at their solar power and
battery % sensors.

You need two sensors: **solar power** and **Powerwall charge %**.

### Wall Connector

**Settings → Devices & services → Add integration → Tesla Wall Connector**, then
enter its IP address from your router. This needs a Gen 3 Wall Connector on Wi-Fi.

You need two entities: **power** and **vehicle connected**.

### Hyundai Bluelink

1. Install [HACS](https://hacs.xyz/) if you don't have it.
2. **HACS → search "Kia Uvo" → Download**, then restart Home Assistant.
3. **Settings → Devices & services → Add integration → Kia Uvo**, then choose
   **Hyundai**, region **USA**, and enter your email, password and PIN.
4. Leave the update intervals at their defaults. Asking the car for data more often
   drains its 12 V battery.

You need one entity: **EV battery level**.

### Override switch (optional)

**Settings → Devices & services → Helpers → Create helper → Toggle**, named
something like "EV charger override". While it's on, the add-on leaves charging
alone. Use it when you want to charge fully overnight.

## 3. Find your entity IDs

Go to **Settings → Devices & services → Entities** and search for each of these.
Copy the entity ID (for example `sensor.powerwall_solar_power`).

| Add-on option | What to look for |
|---|---|
| `solar_power_entity` | Powerwall "Solar power" (kW) |
| `powerwall_soc_entity` | Powerwall "Charge" (%) |
| `charger_power_entity` | Wall Connector "Power" |
| `plugged_in_entity` | Wall Connector "Vehicle connected" |
| `car_soc_entity` | Ioniq "EV battery level" |
| `override_entity` | Your toggle, e.g. `input_boolean.ev_charger_override` |

Check the metering once: start charging and watch the Wall Connector power rise.
If it stays at 0, the add-on can't tell when the car is charging.

## 4. Install the add-on

**From GitHub:** go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and
add this repository's URL. Newer versions may call add-ons "Apps". Then install
**Solar EV Charger**.

**Without GitHub:** install the **Samba share** or **Advanced SSH & Web Terminal**
add-on and copy the `solar_ev_charger` folder into the `addons` share. Then go to
**Add-on Store → ⋮ → Check for updates**, and it appears under **Local add-ons**.

## 5. Configure and start

1. On the add-on's **Configuration** tab, paste in your entity IDs. The defaults are
   already: Powerwall > 35%, solar > 8 kW, stop at 80%.
2. **Start** the add-on and turn on **Start on boot**.
3. Open the **Log** tab. Within a minute you should see a line such as
   `will start if this lasts: Powerwall at 62% (> 40%)`.
4. Add `sensor.solar_ev_charger` to a dashboard to see what it's doing.
