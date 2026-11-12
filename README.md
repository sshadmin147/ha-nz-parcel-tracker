# NZ Parcel Tracker

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom Home Assistant integration that tracks parcels from New Zealand couriers. No account is needed: add each tracking code you want to follow. It currently supports [NZ Post](https://www.nzpost.co.nz/tools/tracking) [Aramex New Zealand](https://www.aramex.co.nz/tools/track), [Post Haste](https://posthaste.co.nz/track/) and [NZ Couriers](https://nzcouriers.co.nz/track/) customer labels and [DHL](https://www.dhl.com/) (with your own free DHL API key); the code is split so other couriers can be added (see [Adding a courier](CLAUDE.md#adding-a-courier)).

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Supported couriers](#supported-couriers)
- [Installation](#installation)
- [Configuration](#configuration)
- [Options](#options)
- [Dynamic polling](#dynamic-polling)
- [Removal](#removal)
- [Sensors](#sensors)
- [Parcel status reference](#parcel-status-reference)
- [Events](#events)
- [Services](#services)
- [Examples](#examples)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)
- [Disclaimer](#disclaimer)
- [Contributing](#contributing)
- [License](#license)
- [Credits](#credits)

## Features

- Track any number of parcels by tracking code, with no account needed
- Per-parcel sensor with the status, the courier's latest status text and a link to the courier's public tracker
- Summary sensors: incoming parcels, next delivery, recently delivered parcels
- Read-only **Deliveries** calendar; NZ Post does not currently expose delivery dates, so it stays empty until a courier provides them
- `nz_parcel_tracker.track_parcel` / `nz_parcel_tracker.untrack_parcel` services, so a dashboard button can add a parcel
- Events and device triggers for no-code automations (parcel registered, status changed, delivered)
- Opt-in per-parcel status history
- Manual refresh button and a diagnostic last-update sensor

## Requirements

- Home Assistant 2025.12 or newer
- A parcel and its tracking code (from the shipping confirmation email or the missed-delivery card)

## Supported couriers

| Courier | Key | Tracking code | Provides |
|---|---|---|---|
| NZ Post | `nz_post` | 8 to 30 letters and numbers (spaces and hyphens are ignored) | Status, status history and a link to the public tracker. No delivery window, pickup point, sender, receiver, weight or dimensions. |
| Aramex (New Zealand) | `aramex` | 8 to 30 letters and numbers | Status, status history, a link to the public tracker and Aramex's estimated delivery date (an all-day window, shown on the calendar). No pickup point, sender, receiver, weight or dimensions. |
| Post Haste (customer labels) | `post_haste` | The customer number and the consignment ID, separated by a space, for example `2020119 DESX0026044` (both are in the tracking link the sender emails) | Status, status history and a link to the public tracker. No delivery window, pickup point, sender, receiver, weight or dimensions. Prepaid-ticket and charge-label consignments are not supported. || NZ Couriers (customer labels) | `nz_couriers` | The customer number and the consignment ID, separated by a space, for example `3351469 AGAG064544` (both are in the tracking link the sender emails) | Status, status history and a link to the public tracker. A parcel that is delivered, picked up again and redelivered shows as delivered at the last delivery. No delivery window, pickup point, sender, receiver, weight or dimensions. Prepaid-ticket, charge-label and barcode consignments are not supported. |
| DHL | `dhl` | 8 to 30 letters and numbers, for example a 10 digit Express waybill or `JJD...` | Status (pre-transit, in transit, delivered, problem), status history, DHL's delivery estimate when it gives one (shown on the calendar) and weight when known. **Needs your own DHL API key**, see [Setting up DHL](docs/dhl-api-key.md). No pickup point, sender, receiver or tracking link. |

> **Post Haste and NZ Couriers: customer labels only.** These two couriers have several kinds of tracking number (customer-printed labels, prepaid tickets, charge labels, barcodes). Only **customer labels** are supported, the ones tracked by a customer number plus a consignment ID, as in the tracking link a sender emails you. Prepaid-ticket, charge-label and barcode consignments cannot be tracked yet. DHL, NZ Post and Aramex are not affected.

You always choose the courier a parcel is with; it is never guessed from the code. Couriers use similar-looking codes, so guessing would sometimes be wrong.

## Installation

### HACS (custom repository)

1. Open HACS, choose **Custom repositories** from the menu, and add this repository's URL with the category **Integration**.
2. Search for **NZ Parcel Tracker**, install it, and restart Home Assistant.

### Manual

Copy `custom_components/nz_parcel_tracker` into your `config/custom_components/` folder and restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=nz_parcel_tracker)

Or set it up by hand: add the integration via **Settings → Devices & Services → Add Integration → NZ Parcel Tracker**. The only thing it asks is an optional **DHL API key**; choose **Skip for now** if you do not use DHL or do not have a key yet. The step-by-step guide to getting one is in [Setting up DHL](docs/dhl-api-key.md). Everything else needs no setup, and a skipped key can be added later from **Configure**.

Then add parcels via the integration's **Configure** dialog (choose the courier, then enter the tracking number), the [`nz_parcel_tracker.track_parcel`](#services) service, or a [dashboard button](examples/dashboards/add_parcel_card.yaml). The tracking code is on your shipping confirmation email or the missed-delivery card.

## Options

Open **Configure** on the integration entry:

| Section | Option | Default | Description |
|---|---|---|---|
| DHL | Add or change / Remove a DHL API key | none | Store, replace or remove the DHL API key (see [Setting up DHL](docs/dhl-api-key.md)). Changing a key reloads the integration. DHL only appears in the courier list while a key is saved. |
| Parcels | Add a parcel / Remove parcels | none | Add a parcel by choosing its courier and entering the tracking number, or remove tracked parcels. Changes apply immediately, no restart. |
| Delivered parcels | Filter by / amount | last 7 days | How long delivered parcels stay visible on the delivered sensor. |
| Parcel history | Include status history | off | Adds a `history` attribute per parcel with each status update. |

Polling isn't one of these settings: the integration polls on a dynamic, status-driven schedule with nothing to configure.

## Dynamic polling

The integration adjusts its own cadence to what your tracked parcels are doing:

- **Quiet hours:** no polling between 00:00 and 06:00 local time, aside from one catch-up check at each end of that window, so an overnight update is never missed.
- **Hot (every 15 minutes):** while any tracked parcel is out for delivery today. A courier that gives no confirmed delivery window (NZ Post does not) starts this as soon as a parcel is out for delivery.
- **Normal (every 45 minutes):** for anything else still on its way.
- **Fully paused:** once every tracked parcel has been delivered, or nothing is tracked at all, polling stops until you add a parcel back. Adding one always triggers an immediate check.
- A small, fixed per-install offset is added on top, so installs don't all poll at exactly the same second.

## Removal

Standard HA removal applies: **Settings → Devices & Services → NZ Parcel Tracker → ⋮ → Delete**. Nothing is stored on the couriers' side.

## Sensors

| Entity | Description |
|---|---|
| `sensor.nz_parcel_tracker_incoming_parcels` | Number of active tracked parcels, full list under the `parcels` attribute |
| `sensor.nz_parcel_tracker_parcel_<code>` | One per tracked parcel; state is the canonical status, attributes carry the full normalised parcel |
| `sensor.nz_parcel_tracker_next_delivery` | Earliest confirmed delivery moment; empty unless a courier provides one (NZ Post does not) |
| `sensor.nz_parcel_tracker_delivered_parcels` | Recently delivered parcels (see the retention option) |
| `calendar.nz_parcel_tracker_deliveries` | Read-only calendar of expected deliveries, no extra API calls |
| `sensor.nz_parcel_tracker_last_successful_update` | Diagnostic: when the couriers were last polled successfully |

A delivered parcel moves from its per-parcel sensor to the delivered sensor automatically.

## Parcel status reference

The `status` field is one of:

| Status | Meaning |
|---|---|
| `registered` | Announced to / received by the courier |
| `in_transit` | In the sorting network |
| `out_for_delivery` | With the courier today |
| `delivered` | Delivered |
| `problem` | The courier reports a delay or a delivery attempt that did not succeed |
| `unknown` | Not yet scanned, or a status that is not mapped yet |

The courier's own human-readable text is always available as `raw_status`, and the courier's name as `carrier`.

## Events

The integration fires these on the event bus (also available as device triggers on the NZ Parcel Tracker device):

| Event | When |
|---|---|
| `nz_parcel_tracker_parcel_registered` | A new parcel appears in the active list |
| `nz_parcel_tracker_parcel_status_changed` | A parcel's status changes (`old_status` / `new_status` in the payload), except the final hop to delivered |
| `nz_parcel_tracker_parcel_delivered` | A parcel is delivered |

Every payload is the full normalised parcel plus the hub's `device_id`. Events are suppressed on the first refresh after start-up. A courier with no confirmed delivery window (NZ Post) never emits a delivery-time event.

## Services

| Service | Fields | Description |
|---|---|---|
| `nz_parcel_tracker.track_parcel` | `tracking_code`, `carrier` (required) | Start tracking a parcel. `carrier` is the courier key (`nz_post`, `aramex`, `post_haste`, `nz_couriers`, `dhl`) and the code must fit that courier (see [Supported couriers](#supported-couriers)); web addresses are rejected |
| `nz_parcel_tracker.untrack_parcel` | `tracking_code` | Stop tracking a parcel |

## Examples

Ready-to-paste automations and dashboard snippets live in [`examples/`](examples/), including tracking a new parcel straight from a dashboard.

## Debugging

```yaml
logger:
  logs:
    custom_components.nz_parcel_tracker: debug
```

## Troubleshooting

- **A parcel shows `unknown`:** the courier has not scanned it yet (NZ Post's API answers `not_found` until the first scan), or the code is wrong. It will pick up automatically once scanned.
- **"That looks like a web address" or "does not look like a tracking code":** enter just the tracking number from your shipping email, not the tracking link. For NZ Post it should be 8 to 30 letters and numbers.
- **A status logs "Unrecognised <courier> status":** please open an issue on this repository with the logged line so the mapping can be extended.

## Disclaimer

This is an independent, community-built project. It is not affiliated with, endorsed by, sponsored by, or supported by NZ Post, any other courier it supports, Home Assistant, or any other third party referenced in this project. Please don't contact a courier for support with this integration.

All third-party trademarks, trade names, product names, logos, and other brand assets are the property of their respective owners. References to them are solely to identify the relevant carrier or service and do not imply affiliation, sponsorship, or endorsement. Nothing in this project grants or implies any licence or right to use third-party brand assets.

This integration may rely on public, unofficial, or undocumented carrier interfaces. These may change or be withdrawn without notice and may be subject to the couriers' terms. Data is sent only to the courier's own services; this project operates no servers of its own. You are responsible for ensuring that your use complies with applicable law and those terms. Use is at your own risk; see the [licence](LICENSE) for warranty limitations.

For NZ Post, this integration uses the same public tracking endpoint as the NZ Post consumer website.

## Contributing

Pull requests and issues are welcome. Please open an issue before submitting a large change.

## License

[MIT](LICENSE)

## Credits

This project is a fork of [ha-nz-post](https://github.com/ha-parcel-integrations/ha-nz-post) by [@peter-mdf](https://github.com/peter-mdf) and the [ha-parcel-integrations](https://github.com/ha-parcel-integrations) contributors, released under the MIT licence. Thank you for the original integration this builds on.
