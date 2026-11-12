# Working in this repository

Home Assistant custom integration for tracking parcels from New Zealand
couriers, domain `nz_parcel_tracker`. A fork of
[ha-nz-post](https://github.com/ha-parcel-integrations/ha-nz-post) (MIT),
stripped back to its own tracking logic: no dependency on any other
integration, shared CI or suite tooling. Not published to HACS.

NZ Post, Aramex (New Zealand only), Post Haste (customer labels only) and DHL
(official API, needs the user's own key) are the couriers so far. Everything
outside `carriers/<courier>/` is courier independent. Keep it that way: no courier names, endpoints, payload
fields or status wording in the core.

## Layout

All code is in `custom_components/nz_parcel_tracker/`.

Courier independent (the core):

| File | Role |
|---|---|
| `__init__.py` | Entry setup; builds the couriers and the coordinator |
| `coordinator.py` | Polls every tracked code through its own courier, builds the parcel lists, fires events, picks the dynamic poll interval |
| `parcels.py` | Pure helpers: `build_parcel` (the shared parcel shape), timestamps, history sorting, sorting, the delivered filter, the unmapped-status warning |
| `codes.py` | Tracking code helpers: normalise, link detection, validation against the registered couriers |
| `config_flow.py` | Hub creation and the options flow (parcels, delivered filter, history) |
| `sensor.py`, `button.py`, `calendar.py` | The entities |
| `services.py` | `track_parcel` (required `carrier`) / `untrack_parcel` |
| `device.py`, `device_trigger.py`, `diagnostics.py` | Device info, device triggers, redacted diagnostics |
| `const.py` | Domain, option keys, polling constants, the shared `ParcelStatus` values |

Couriers, in `carriers/`:

| File | Role |
|---|---|
| `carriers/base.py` | The `Carrier` interface and `CarrierApiError` |
| `carriers/__init__.py` | `CARRIERS` registry, `create_carriers` |
| `carriers/aramex/` | Aramex NZ: same layout as `nz_post/`; `async_prepare` loads the NZ time zone for the date-only ETA |
| `carriers/dhl/` | DHL Unified Shipment Tracking API: `api.py` (client with a 5 s call spacer), `mapping.py`, `const.py`, `__init__.py` (`DHLCarrier`) |
| `carriers/post_haste/` | Post Haste: scrapes the public HTML tracking page; the tracking code is `<customer number> <consignment id>` |
| `carriers/nz_post/` | NZ Post: `api.py` (HTTP client), `mapping.py` (status maps and normalising), `const.py` (endpoints), `__init__.py` (`NZPostCarrier`) |

Stored parcels are `{tracking_code, carrier}` dicts in the entry options. An
entry without `carrier` means `nz_post` (the only courier when it was added).

## Adding a courier

1. Create `carriers/<key>/` with an API client (raise a `CarrierApiError`
   subclass with `carrier_name` set), a status mapping and a `Carrier` subclass.
   Build every parcel with `parcels.build_parcel` and call
   `parcels.warn_unmapped_status` for statuses you do not map.
2. Implement `matches_code` (a class method) so a code can be validated for
   this courier without a session. The user always chooses the courier (options
   form dropdown, required `carrier` on `track_parcel`); codes are never used to
   guess it, because couriers share code shapes. Override `async_prepare` for
   setup that needs the event loop. A courier that needs a secret sets
   `config_key` (the entry data key) and implements `async_validate_config`; it
   is then only `available()` once the user has saved it, and the setup flow, the
   options flow, the courier dropdown and the service all follow from that. A
   courier whose terms require attribution sets `attribution`.
3. List the class in `CARRIERS` in `carriers/__init__.py` and add its key to the
   `carrier` selector in `services.yaml` and the `selector.carrier` names in
   `strings.json` and `translations/en.json`.
4. Add its payload field names to `Carrier.redact_keys` so diagnostics redact
   them.
5. Add tests: the mapping, the client (see `tests/test_api.py`) and the code
   format. `tests/test_carriers.py` drives the core with a fake second courier;
   extend it if the core grows a courier-dependent path.
6. Update `README.md` (the *Supported couriers* table) and this file.

Dynamic polling, options, entities, events and services are documented in
`README.md`; keep that file and this one in step with any code change.
`TODO.md` lists the outstanding work (release steps, robustness, adding other
couriers); update it when something is done or a new task turns up.

## Tripwires

- **First refresh in `__init__.py`, before `async_forward_entry_setups`.** From
  a forwarded platform HA can't catch `ConfigEntryNotReady` and half-sets-up the
  entry. Runtime-only; tests don't catch a regression.
- **The setup stale-entity sweep is scoped to `domain == "sensor"` and skips
  `non_parcel_unique_ids`.** Otherwise it deletes the refresh button and the
  summary and diagnostic sensors. Add any new non-parcel sensor's unique_id to
  that set.
- **Per-parcel sensors are removed by the summary sensor** via
  `entity_registry.async_remove`. Self-removal races and leaves ghosts.
- **Services only exist while the config entry is loaded.** They are registered
  in `async_setup_entry`, so a failed first refresh also makes them unavailable.
- **Tracking codes are shape-checked, not verified.** `valid_tracking_code` in
  `codes.py` (used by the options flow and `track_parcel`) accepts a code if a
  registered courier's `matches_code` does, and `looks_like_link` rejects pasted
  web addresses with their own message. For NZ Post that means 8 to 30 letters
  and digits once spaces and hyphens are ignored. A code that passes can still
  be unknown to the courier. Codes already stored are not re-checked on load
  (see `TODO.md`).
- **The core must stay courier independent.** `tests/test_carriers.py` runs the
  coordinator with a fake second courier; a courier name, endpoint or payload
  field in the core will show up there or in review.

## NZ Post specifics (`carriers/nz_post/`)

NZ Post is a keyless, code-based tracker. It has no confirmed ETA, pickup
point, sender/receiver, weight or dimensions, so those fields are intentionally
`None`. `history` and `url` are the only optional fields it fills; `url` is the
confirmed `?trackid=<code>` deep link (`TRACKING_URL_BASE` in `carriers/nz_post/const.py`). The
public payload contains recipient and operational location fields, so
`raw` keeps only a cleaned event subset and diagnostics redact all tracking,
signer and depot/run details.

Status mapping is keyed on NZ Post's own display text (`status`, present on
every event), with `edifact_code` as a fallback for an event that arrives
without it; both maps hold only wording NZ Post itself uses. `Delayed` (`40`)
and `Delivery attempted - refer to card` (`52`) map to `problem`; border-agency
events (`With border agency`, `Held for clearance`, `Released for delivery`)
stay `in_transit`. `Handed over` (`144`) and `Arrival at sorting centre`
(`5042`) were confirmed on real parcels on 2026-10-17. `Handed over` maps to
`in_transit`, not `at_pickup_point`: its own description reads "handed over and
will be ready for collection soon", so the parcel is on its way to a collection
point rather than waiting at one.

`AT_PICKUP_POINT` is therefore unreachable on purpose. A genuinely
collection-ready code would make it reachable and would need an
`awaiting_pickup` sensor first. Every collection-ready or other delivery-attempt
code whose wording has not been seen on a real parcel stays unmapped, falling
through to `unknown` plus a one-shot warning. Event timestamps are real UTC
(`Z`); don't add a timezone workaround.

## Running tests

```
python -m pytest tests/ --cov=custom_components.nz_parcel_tracker
```

Coverage must stay **above 95%**. Run before committing.

Install the dev requirements from `requirements-dev.txt` first (a virtual
environment is best).

On native Windows, `pytest-homeassistant-custom-component` fails to import
because Home Assistant needs the Unix-only `fcntl` and `resource` modules.
`tests/windows_stubs/` holds minimal stand-ins; put that folder on `PYTHONPATH`:

```
set PYTHONPATH=tests\windows_stubs
python -m pytest tests/ --cov=custom_components.nz_parcel_tracker
```

(PowerShell: `$env:PYTHONPATH = "tests\windows_stubs"`.) `tests/conftest.py`
already works around the Windows socket and DNS-resolver limits. On Linux or
WSL no stubs are needed.

## Aramex specifics (`carriers/aramex/`)

Ported from [ha-aramex](https://github.com/ha-parcel-integrations/ha-aramex)
(MIT, copyright line added to `LICENSE`), New Zealand host only. Keyless; one GET
per label; a label with no `Scans` list is "unknown or not scanned yet" (`None`).
Status mapping is keyed on scan codes (`PP8`, `ONB`, `R36`...); unknown codes
give `unknown` plus a one-shot warning. `DeliveryETADate` (`DD/MM/YYYY`) is a
booking-time estimate and becomes an all-day `planned_from`/`planned_to` in
`Pacific/Auckland`, cleared once delivered; it is not corrected for delays. The
payload carries recipient data, so `raw` keeps only code, text and timestamp and
`sender`/`receiver`/`weight`/`dimensions`/`pickup_point` stay `None`. The status
codes and label formats come from the upstream repo and have not been checked
against real parcels here.

## Post Haste specifics (`carriers/post_haste/`)

Post Haste has no JSON API for customer-printed labels, so the client reads the
server-rendered tracking page
(`tools.posthaste.co.nz/phl/servlet/ITNG_TAndTServlet?Key_Type=CustomerLabel`)
with a regex on the `mk-transaction-title` headings: **layout changes will break
it**, which is why a page with no events and no "no information available"
message raises an error instead of reading as "unknown". The page is keyed on two
values, so the stored `tracking_code` is `<customer number> <consignment id>`
(space or hyphen). Event times are NZ local (`11:34AM 24/8/2026`), converted in
`Pacific/Auckland` via `async_prepare`. Statuses are keyed on the entry title:
`Pickup` (in transit), `On Board` (out for delivery, inferred from timing),
`Delivery` (delivered); anything else is `unknown` plus a one-shot warning. The
entry text names the courier and the signer, so only title and time are kept.
Verified against one real delivered parcel (2026-11-12). Post Haste's prepaid
ticket (`product_code` + `serial_number`), charge label (`label_number`) and
contract bag lookups are not supported, and its newer JSON endpoint
(`web-api.freightways.makerdesign.co.nz/track?query=`) returned nothing for the
customer label we tried.

## DHL specifics (`carriers/dhl/`)

Uses DHL's official Unified Shipment Tracking API (`api-eu.dhl.com/track/shipments`)
with the user's own `DHL-API-Key`, stored in the config entry **data**
(`dhl_api_key`) and never in options, logs or diagnostics. The key is asked for
at setup with a **Skip** choice and can be added, changed or removed from the
options; saving a change reloads the entry because the couriers are built from
the entry data. Without a key `DHLCarrier.available()` is false, so it is left out
of `create_carriers`, the courier dropdown and `track_parcel`; stored DHL
parcels are then skipped with a warning (a removed key does not delete them).
The standard key allows 250 calls a day and one call every 5 seconds, so
`DHLApiClient` serialises requests behind a lock and sleeps to keep 5 s between
calls, even though the coordinator gathers fetches. Setup and key checks cost
real calls. Status is DHL's five-value `statusCode` only (`pre-transit`,
`transit`, `delivered`, `failure`, `unknown`): `out_for_delivery` is never
reached until real parcels show what DHL's finer `status` text means, so a DHL
parcel does not get the hot 15 minute poll. Timestamps are passed through as DHL
sends them; one without an offset is local to the event's place and is not
relabelled. Addresses and free text are dropped from `raw`. `url` is `None` (no
confirmed deep link). DHL's terms need the attribution
`DHL data delivered by Deutsche Post DHL Group` on every entity, and delivered
shipments vanish about 30 days after delivery.
This was built from DHL's published API description and the ha-dhl project,
and has not been run against a real DHL key or a real NZ parcel. The keyless DHL
Express backend in ha-dhl is deliberately not used: it relies on a token
extracted from DHL's mobile app.
