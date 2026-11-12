# NZ Parcel Tracker: technical reference

The details behind the [README](../README.md): couriers and their codes, entities, events, services, polling and debugging. For how to add a courier or work on the code, see [`CLAUDE.md`](../CLAUDE.md).

## Contents

- [Supported couriers in detail](#supported-couriers-in-detail)
- [Configuration and options](#configuration-and-options)
- [Dynamic polling](#dynamic-polling)
- [Sensors and entities](#sensors-and-entities)
- [Parcel status reference](#parcel-status-reference)
- [Events and device triggers](#events-and-device-triggers)
- [Services](#services)
- [How each courier is read](#how-each-courier-is-read)
- [Privacy and diagnostics](#privacy-and-diagnostics)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)

## Supported couriers in detail

You always choose the courier a parcel is with; it is never guessed from the code, because couriers use similar-looking codes.

| Courier | Key | Tracking code | Provides |
|---|---|---|---|
| NZ Post | `nz_post` | 8 to 30 letters and numbers (spaces and hyphens are ignored) | Status, status history and a link to the public tracker. No delivery window, pickup point, sender, receiver, weight or dimensions. |
| Aramex (New Zealand) | `aramex` | 8 to 30 letters and numbers | Status, status history, a link to the public tracker and Aramex's estimated delivery date (an all-day window, shown on the calendar). No pickup point, sender, receiver, weight or dimensions. |
| Post Haste (customer labels) | `post_haste` | The customer number and the consignment ID, separated by a space or hyphen, for example `2020119 DESX0026044` | Status, status history and a link to the public tracker. No delivery window, pickup point, sender, receiver, weight or dimensions. |
| NZ Couriers (customer labels) | `nz_couriers` | The customer number and the consignment ID, separated by a space or hyphen, for example `3351469 AGAG064544` | Status, status history and a link to the public tracker. A parcel that is delivered, picked up again and redelivered shows as delivered at the last delivery. No delivery window, pickup point, sender, receiver, weight or dimensions. |
| DHL | `dhl` | 8 to 30 letters and numbers, for example a 10 digit Express waybill or `JJD...` | Status (pre-transit, in transit, delivered, problem), status history, DHL's delivery estimate when it gives one (shown on the calendar) and weight when known. **Needs your own DHL API key** ([guide](dhl-api-key.md)). No pickup point, sender, receiver or tracking link. |

> **Post Haste and NZ Couriers: customer labels only.** These two couriers have several kinds of tracking number (customer-printed labels, prepaid tickets, charge labels, barcodes). Only **customer labels** are supported, the ones tracked by a customer number plus a consignment ID, as in the tracking link a sender emails you. Prepaid-ticket, charge-label and barcode consignments cannot be tracked yet.

## Configuration and options

Setup asks only for an optional DHL API key (with a **Skip for now** choice). Everything else needs no setup.

Open **Configure** on the integration entry:

| Section | Option | Default | Description |
|---|---|---|---|
| DHL | Add or change / Remove a DHL API key | none | Store, replace or remove the DHL API key ([guide](dhl-api-key.md)). Changing a key reloads the integration. DHL only appears in the courier list while a key is saved. |
| Parcels | Add a parcel / Remove parcels | none | Add a parcel by choosing its courier and entering the tracking number, or remove tracked parcels. Changes apply immediately, no restart. |
| Delivered parcels | Filter by / amount | last 7 days | How long delivered parcels stay visible on the delivered sensor. |
| Parcel history | Include status history | off | Adds a `history` attribute per parcel with each status update. |

Polling is not a setting: the integration polls on a dynamic, status-driven schedule with nothing to configure.

Stored parcels are `{tracking_code, carrier}` entries in the config entry options. An entry without `carrier` means NZ Post (the only courier when it was first added). The DHL API key is stored in the config entry data, not the options.

## Dynamic polling

The integration adjusts its own cadence to what your tracked parcels are doing:

- **Quiet hours:** no polling between 00:00 and 06:00 local time, aside from one catch-up check at each end of that window, so an overnight update is never missed.
- **Hot (every 15 minutes):** while any tracked parcel is out for delivery today. A courier that gives no confirmed delivery window (NZ Post does not) starts this as soon as a parcel is out for delivery.
- **Normal (every 45 minutes):** for anything else still on its way.
- **Fully paused:** once every tracked parcel has been delivered, or nothing is tracked at all, polling stops until you add a parcel back. Adding one always triggers an immediate check.
- A small, fixed per-install offset is added on top, so installs don't all poll at exactly the same second.

DHL's standard API key allows one call every 5 seconds and 250 calls a day. The integration spaces its DHL calls to stay under that, and a delivered parcel stops being asked about.

## Sensors and entities

| Entity | Description |
|---|---|
| `sensor.nz_parcel_tracker_incoming_parcels` | Number of active tracked parcels, full list under the `parcels` attribute |
| `sensor.nz_parcel_tracker_parcel_<code>` | One per tracked parcel; state is the canonical status, attributes carry the full normalised parcel |
| `sensor.nz_parcel_tracker_next_delivery` | Earliest confirmed delivery moment; empty unless a courier provides one (NZ Post, Post Haste and NZ Couriers do not) |
| `sensor.nz_parcel_tracker_delivered_parcels` | Recently delivered parcels (see the retention option) |
| `calendar.nz_parcel_tracker_deliveries` | Read-only calendar of expected deliveries, no extra API calls |
| `sensor.nz_parcel_tracker_last_successful_update` | Diagnostic: when the couriers were last polled successfully |
| Refresh button | Polls every tracked parcel now |

A delivered parcel moves from its per-parcel sensor to the delivered sensor automatically. Every entity carries the attribution "Data provided by the couriers' public tracking services"; with DHL set up it also carries "DHL data delivered by Deutsche Post DHL Group".

## Parcel status reference

The `status` field is one of:

| Status | Meaning |
|---|---|
| `registered` | Announced to / received by the courier |
| `in_transit` | In the courier's network |
| `out_for_delivery` | With the courier today |
| `delivered` | Delivered |
| `problem` | The courier reports a delay or a delivery attempt that did not succeed |
| `unknown` | Not yet scanned, or a status that is not mapped yet |

The courier's own human-readable text is always available as `raw_status`, and the courier's name as `carrier`. Other fields every parcel carries: `barcode`, `sender`, `receiver`, `delivered`, `delivered_at`, `planned_from`, `planned_to`, `pickup`, `pickup_point`, `url`, `weight`, `dimensions`, `history` and `raw`. A field a courier cannot provide is `null`, never missing.

## Events and device triggers

The integration fires these on the event bus (also available as device triggers on the NZ Parcel Tracker device):

| Event | When |
|---|---|
| `nz_parcel_tracker_parcel_registered` | A new parcel appears in the active list |
| `nz_parcel_tracker_parcel_status_changed` | A parcel's status changes (`old_status` / `new_status` in the payload), except the final hop to delivered |
| `nz_parcel_tracker_parcel_delivered` | A parcel is delivered |

Every payload is the full normalised parcel plus the hub's `device_id`. Events are suppressed on the first refresh after start-up. A courier with no confirmed delivery window never emits a delivery-time event.

## Services

| Service | Fields | Description |
|---|---|---|
| `nz_parcel_tracker.track_parcel` | `tracking_code`, `carrier` (both required) | Start tracking a parcel. `carrier` is the courier key (`nz_post`, `aramex`, `post_haste`, `nz_couriers`, `dhl`) and the code must fit that courier; web addresses are rejected. DHL is refused until a DHL API key is saved. |
| `nz_parcel_tracker.untrack_parcel` | `tracking_code` | Stop tracking a parcel |

The services exist only while the integration is loaded. Tracking the same code twice is a harmless no-op.

## How each courier is read

All of these use public tracking interfaces. None needs an account, and only DHL needs a key.

- **NZ Post:** the same public tracking endpoint as the NZ Post consumer website, one request per code. A code NZ Post has not scanned yet is "unknown".
- **Aramex (New Zealand):** the public tracking endpoint on the Aramex NZ website, one request per label. Aramex's estimated delivery date is a booking-time estimate and is not corrected if the parcel is delayed.
- **Post Haste and NZ Couriers:** both are Freightways brands with the same customer-label tracking page, which is read as a web page (there is no JSON API for customer labels). Event times are New Zealand local time. The status comes from the newest non-informational event, so a parcel that was delivered, picked up again and delivered once more reads as delivered at the last delivery. If the page's layout changes, the courier reports an error rather than showing "unknown".
- **DHL:** DHL's official Unified Shipment Tracking API with your own `DHL-API-Key`. DHL only reports pre-transit, in transit, delivered and failure, so a DHL parcel never shows `out_for_delivery`. Its terms apply: track your own parcels, credit DHL (done on every entity), and delivered shipments disappear about 30 days after delivery.

## Privacy and diagnostics

Courier payloads contain recipient and operational details (names, addresses, who signed). Only the fields needed for status are kept; everything else is dropped before it is stored. Diagnostics redact tracking codes, barcodes, links and each courier's identifying fields. The DHL API key is never logged or included in diagnostics. Data is sent only to the courier's own services; the project operates no servers.

## Debugging

```yaml
logger:
  logs:
    custom_components.nz_parcel_tracker: debug
```

## Troubleshooting

- **A parcel shows `unknown`:** the courier has not scanned it yet, or the code is wrong. It will pick up automatically once scanned. A Post Haste or NZ Couriers code must be the customer number and consignment ID together.
- **"That looks like a web address" or "does not look like a tracking number for the chosen courier":** enter just the tracking number from your shipping email, not the tracking link, and check you chose the right courier.
- **A status logs "Unrecognised <courier> status":** please open an issue on this repository with the logged line so the mapping can be extended.
- **A Post Haste or NZ Couriers parcel suddenly errors:** the courier may have changed its web page. Open an issue with the log line.
- **DHL is missing from the courier list:** no DHL API key is saved. Add one from **Configure** (see the [DHL guide](dhl-api-key.md)).
- **DHL parcels stopped updating:** the key may have been removed or rejected, or DHL's daily allowance was used up. Updates resume when the key is valid and the allowance resets.
