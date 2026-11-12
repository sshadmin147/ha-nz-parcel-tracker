# TODO

What is still to do for this fork. Tick items off or delete them as they are done.

## 1. Get the repo ready to publish

- [ ] `git init`, create `sshadmin147/ha-nz-parcel-tracker` on GitHub and push. This folder is not a git repository yet, so nothing has been committed.
- [ ] Add your own copyright line above the original in `LICENSE`. Keep the original "ha-nz-post contributors" line; the MIT licence requires it.
- [ ] Put the real repository URL in the README's HACS install steps (it currently says "this repository's URL").
- [ ] Reset the version in `manifest.json`. It still says `0.11.2`, which is the original project's number. Pick a starting version for the fork, for example `0.1.0`.
- [ ] Check `custom_components/nz_parcel_tracker/brand/icon.png` is acceptable to ship. It was inherited from the original.

## 2. Tests and CI

- [x] The suite runs and passes (177 tests, about 98% coverage) on Windows using the stand-ins in `tests/windows_stubs/`; see `CLAUDE.md`. Still worth one run on Linux or WSL before publishing, since that is what CI will use.
- [ ] Keep coverage above 95% as couriers are added.
- [ ] Run `ruff` against `ruff.toml` and fix anything it reports. Some long lines were added.
- [ ] Write a GitHub Actions workflow of our own. The original `.github/` folder was removed because it called the original organisation's shared workflows. A minimal one: run the tests, run ruff, run `hassfest`, and run the HACS validation action.

## 3. Release steps (when ready to publish)

`hacs.json` is set up for zip releases (`"zip_release": true`, `"filename": "nz_parcel_tracker.zip"`), so each release needs a zip attached.

- [ ] Bump `version` in `custom_components/nz_parcel_tracker/manifest.json`.
- [ ] Update the README and `CLAUDE.md` for the change.
- [ ] Zip the **contents** of `custom_components/nz_parcel_tracker/` (so `manifest.json` is at the top of the zip) as `nz_parcel_tracker.zip`.
- [ ] Tag the commit (`vX.Y.Z`), create a GitHub release, and attach the zip.
- [ ] Automate the zip and release in the workflow above once the manual steps are stable.
- [ ] Test the install from HACS as a custom repository (category: Integration) on a spare HA instance first.
- [ ] Not now: consider submitting to the HACS default list. The integration needs a distinct name and a stable release history first.

## 4. Make the integration more robust

- [ ] **A bad stored code must not stop setup.** Today the entry goes to `setup_retry` ("unreachable for all tracked parcels") when every stored code errors on the first refresh, and the `track_parcel` / `untrack_parcel` services disappear until it loads. Options: register the services in `async_setup` so they always exist; skip or flag a code that returns HTTP 400 instead of failing the whole entry; raise a Home Assistant repair issue naming the bad code.
- [ ] **Clean up already-stored bad codes** when the entry loads (for example a pasted link saved by an older version).
- [ ] **Remove delivered parcels from the stored list automatically.** The integration stops polling them but never removes them, so the stored list grows.
- [ ] Find out what NZ Post's API returns for expired or purged codes (the 400s) and handle that case explicitly.
- [ ] Decide whether the NZ Post 8 to 30 character rule is right. It is based on codes seen so far (`00794210392837795918`, `FX0003653338`, `LH440267135AU`). Loosen it if a real code is rejected.
- [ ] Decide on translation keys for service errors. The service currently raises plain-text `ServiceValidationError` messages.

## 5. Add other couriers (the main goal)

Done: the code is split into a courier-independent core and a `carriers/` package. NZ Post is `carriers/nz_post/`, behind the `Carrier` interface in `carriers/base.py`. Parcels are stored as `{tracking_code, carrier}`, the user always chooses the courier (a dropdown in the options form, a required `carrier` on `track_parcel`; nothing is auto-detected), the device and entities are named `nz_parcel_tracker`, and `CLAUDE.md` has the steps for adding a courier.

- [x] First extra courier: Aramex New Zealand (`carriers/aramex/`), ported from ha-aramex. Still to do: check its scan codes, label formats and the ETA handling against real parcels (none have been tracked through this fork yet).
- [x] Post Haste (customer labels) added by scraping its tracking page; checked against one real delivered parcel. Still to do: other Post Haste label types (prepaid ticket, charge label), the `On Board` / unseen status titles on live parcels, and a check on how fragile the page parsing is over time. The Freightways JSON endpoint `web-api.freightways.makerdesign.co.nz/track?query=` may cover Post Haste, CourierPost and NZ Couriers with one client; find a number it recognises.
- [ ] Pick the next courier (for example CourierPost) and check it has a usable public tracking endpoint and a stable payload before writing any code.
- [ ] Decide whether polling should be per courier (separate rate limits and backoff). The 429 backoff is currently shared across all couriers.
- [ ] Rename the NZ Post specific names that remain in the core if any appear (the core should have none; `tests/test_carriers.py` checks it works with a fake second courier).
- [ ] Update the README (*Supported couriers* table), `CLAUDE.md` and the examples for every courier added.

## 6. Switching my Home Assistant over (when this fork is ready)

My live HA runs the original `nz_post` integration, and some things there depend on its domain name:

- [ ] `script.track_parcel` calls `nz_post.track_parcel` and has the link and format checks that this fork now does itself. Change it to `nz_parcel_tracker.track_parcel` with `carrier: nz_post` (now required) and drop the duplicated checks.
- [ ] `automation.parcel_delivered_notification` triggers on the event `nz_post_parcel_delivered`. It becomes `nz_parcel_tracker_parcel_delivered`.
- [ ] `automation.clean_up_old_parcels` calls `nz_post.untrack_parcel` and reads `sensor.nz_post_incoming_parcels` / `sensor.nz_post_delivered_parcels`, using the `barcode` and `delivered_at` fields of their `parcels` attribute. Update the names (the entities become `sensor.nz_parcel_tracker_incoming_parcels` / `sensor.nz_parcel_tracker_delivered_parcels`), and keep those attribute fields unchanged so it keeps working.
- [ ] Dashboards using `sensor.nz_post_*` entities (they become `sensor.nz_parcel_tracker_*`), plus the Package slot helpers (`input_text.package_slot_1` to `10`).
- [ ] Remove the original `nz_post` integration and its HACS entry first. Both cannot share a parcel list, so there is no in-place migration.

## 7. Small clean-ups

- [ ] Check the `examples/` folder against the new domain and the new tracking code rules. The email-to-tracking example may extract codes that no longer pass validation.
- [ ] Remove `examples/` entries that are not useful to this fork.
- [ ] Decide whether to keep `hacs.json` as it is until publishing.
