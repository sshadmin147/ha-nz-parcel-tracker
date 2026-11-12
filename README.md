# NZ Parcel Tracker

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Track your parcels from New Zealand couriers in Home Assistant. Add a tracking number and the integration keeps an eye on it for you, shows where the parcel is, and can tell you when it is out for delivery or has arrived.

You do not need an account with any courier. The only courier that needs anything extra is DHL, which needs a free key of your own (there is a [step-by-step guide](docs/dhl-api-key.md)).

## What you can do

- Follow as many parcels as you like, from several couriers at once
- See each parcel's status and the courier's own wording, with a link to the courier's tracking page where one exists
- See how many parcels are on their way and which have arrived recently
- Get notified, or run an automation, when a parcel is registered, changes status or is delivered
- Add a parcel from a dashboard button, an automation, or the integration's settings
- Optionally keep a history of each parcel's updates

## Supported couriers

| Courier | What you enter |
|---|---|
| **NZ Post** | The tracking number |
| **Aramex** (New Zealand) | The tracking number, usually starting with `MP` |
| **Post Haste** | The customer number and the consignment ID, with a space between, for example `2020119 DESX0026044` |
| **NZ Couriers** | The customer number and the consignment ID, with a space between, for example `3351469 AGAG064544` |
| **DHL** | The tracking number. Needs your own free DHL key: [how to get one](docs/dhl-api-key.md) |

> **Post Haste and NZ Couriers: customer labels only.** These two couriers have several kinds of tracking number. Only **customer labels** work, the ones that come with a customer number and a consignment ID, as in the tracking link a sender emails you. Prepaid tickets, charge labels and barcodes can't be tracked yet.

You pick the courier yourself when you add a parcel. It is not guessed from the number, because couriers' numbers can look alike.

The couriers' details, such as exactly what each one reports, are in the [technical reference](docs/technical.md).

## Requirements

- Home Assistant 2025.12 or newer
- A parcel and its tracking number (from the shipping email or the missed-delivery card)

## Installation

### HACS (custom repository)

1. Open HACS, choose **Custom repositories** from the menu, and add this repository's URL with the category **Integration**.
2. Search for **NZ Parcel Tracker**, install it, and restart Home Assistant.

### Manual

Copy `custom_components/nz_parcel_tracker` into your `config/custom_components/` folder and restart Home Assistant.

## Setting up

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=nz_parcel_tracker)

Or add it by hand: **Settings → Devices & Services → Add Integration → NZ Parcel Tracker**.

Setup asks one optional question: whether you want to add a **DHL key**. If you don't use DHL, or don't have a key yet, choose **Skip for now**. You can add the key later from **Configure**; the [DHL guide](docs/dhl-api-key.md) walks you through getting one.

## Adding a parcel

Open the integration, choose **Configure**, then **Add a parcel**. Pick the courier, enter the tracking number, and you're done. The number is in your shipping confirmation email or on the missed-delivery card. Paste just the number, not a link.

You can also add and remove parcels with the `nz_parcel_tracker.track_parcel` and `nz_parcel_tracker.untrack_parcel` actions, for example from a dashboard button. See the [examples](examples/) for ready-made ones.

## What you'll see in Home Assistant

- A sensor for each parcel, showing its status
- A sensor counting your incoming parcels, and one listing recently delivered ones
- A calendar of expected deliveries (only for couriers that give a delivery date)
- A refresh button to check everything now

Parcels are checked automatically, more often when one is about to arrive and not at all overnight. Once everything has been delivered, checking stops until you add another parcel.

A parcel's status is one of: registered, in transit, out for delivery, delivered, problem, or unknown (not scanned yet, or not recognised). The sensor names, attributes, events and every setting are listed in the [technical reference](docs/technical.md).

## Settings

Open **Configure** on the integration to:

- add or remove parcels
- add, change or remove your DHL key
- choose how long delivered parcels stay visible (the last 7 days by default)
- turn on a per-parcel history of status updates (off by default)

## Common questions

- **A parcel says "unknown".** The courier probably hasn't scanned it yet, or the number is wrong. It updates by itself once the courier has scanned it.
- **It says my number looks like a web address.** Enter just the tracking number, not the tracking link.
- **DHL isn't in the courier list.** You haven't saved a DHL key yet. Add one from **Configure**; see the [DHL guide](docs/dhl-api-key.md).
- **A Post Haste or NZ Couriers parcel won't track.** Check you are using the customer number and consignment ID together, with a space between, and that it is a customer label.
- **Something else.** The [technical reference](docs/technical.md) has more troubleshooting and how to turn on debug logging.

## Removing

**Settings → Devices & Services → NZ Parcel Tracker → ⋮ → Delete**. Nothing is stored on the couriers' side.

## More information

- [Setting up DHL (getting a DHL key)](docs/dhl-api-key.md)
- [Technical reference](docs/technical.md): couriers in detail, entities, events, services, polling, privacy and debugging
- [Examples](examples/): automations and dashboard cards
- [For contributors](CLAUDE.md): how the code is laid out and how to add a courier

## Disclaimer

This is an independent, community-built project. It is not affiliated with, endorsed by, sponsored by, or supported by NZ Post, any other courier it supports, Home Assistant, or any other third party referenced in this project. Please don't contact a courier for support with this integration.

All third-party trademarks, trade names, product names, logos, and other brand assets are the property of their respective owners. References to them are solely to identify the relevant carrier or service and do not imply affiliation, sponsorship, or endorsement. Nothing in this project grants or implies any licence or right to use third-party brand assets.

This integration may rely on public, unofficial, or undocumented courier interfaces. These may change or be withdrawn without notice and may be subject to the couriers' terms. Data is sent only to the courier's own services; this project operates no servers of its own. You are responsible for ensuring that your use complies with applicable law and those terms. Use is at your own risk; see the [licence](LICENSE) for warranty limitations.

## Contributing

Pull requests and issues are welcome. Please open an issue before submitting a large change.

## License

[MIT](LICENSE)

## Credits

This project is a fork of [ha-nz-post](https://github.com/ha-parcel-integrations/ha-nz-post) by [@peter-mdf](https://github.com/peter-mdf) and the [ha-parcel-integrations](https://github.com/ha-parcel-integrations) contributors, released under the MIT licence. The Aramex support is based on [ha-aramex](https://github.com/ha-parcel-integrations/ha-aramex) from the same project family. Thank you for the original work this builds on.
