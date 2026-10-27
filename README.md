# Solar EV Charger

A Home Assistant add-on that charges a Hyundai Ioniq when your Powerwall or solar can cover it,
using a Tesla Powerwall, a Tesla Wall Connector and Hyundai Bluelink.

See [SETUP.md](SETUP.md) for step-by-step setup, and
[solar_ev_charger/DOCS.md](solar_ev_charger/DOCS.md) for how it works and how
to configure it.

## Install

1. Install the Tesla Powerwall, Tesla Wall Connector and Kia Uvo / Hyundai Bluelink
   (HACS) integrations in Home Assistant.
2. Go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, and add this
   repository's URL. Newer Home Assistant versions may call add-ons "Apps".
3. Install **Solar EV Charger**, set your entity IDs on the Configuration tab, then
   start it and watch the Log tab.

If you'd rather not use GitHub, copy the `solar_ev_charger` folder into your Home
Assistant `/addons` folder (for example with the Samba add-on). It will then appear
under **Local add-ons**.

## Development

The decision logic in `solar_ev_charger/app/controller.py` doesn't depend on Home
Assistant and has unit tests:

```sh
pip install pytest
pytest
```
