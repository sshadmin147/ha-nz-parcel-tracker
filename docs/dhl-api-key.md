# Setting up DHL tracking (getting a DHL API key)

DHL tracking uses DHL's official **Shipment Tracking – Unified** API. DHL gives it
out free, but only with your own API key, so DHL is the one courier in NZ Parcel
Tracker that needs a one-time setup. The other couriers need nothing.

You can do this while installing the integration, or any time later. If you skip it,
everything else works and DHL simply does not appear in the courier list.

## What you need

- A free DHL developer account at [developer.dhl.com](https://developer.dhl.com/).
- A company name on that account. DHL has issued keys to profiles that have a company
  name and has refused them for private profiles. If you only track your own parcels,
  use your own business or trading name if you have one.
- About ten minutes. DHL may take a little while to approve the app.

> DHL's developer site changes from time to time, so button names below may differ
> slightly. The path is always the same: **account → app → add the Shipment Tracking –
> Unified API → copy the key**.

## Step by step

1. Go to [developer.dhl.com](https://developer.dhl.com/) and choose **Sign up** (or
   **Log in** if you already have an account).
2. Fill in the sign-up form. Include a **company name**. Confirm your email address
   from the message DHL sends you, then log in.
3. Open the [Shipment Tracking – Unified API](https://developer.dhl.com/api-reference/shipment-tracking)
   page.
4. Go to **My Apps** and choose to **add (create) an app**.
5. Give the app any name (for example `Home Assistant`) and a short description (for
   example `Track my own parcels in Home Assistant`).
6. When asked which APIs the app should use, tick **Shipment Tracking – Unified**.
7. Submit the app. If DHL needs to approve it, wait for their email; the app then shows
   as approved.
8. Open the app and copy its **API Key** (sometimes labelled **Consumer Key**). This is
   a long string of letters and numbers. You do not need the **Secret**.

## Adding the key to Home Assistant

### During setup

1. Add the integration: **Settings → Devices & Services → Add Integration → NZ Parcel
   Tracker**.
2. Choose **Add a DHL API key** and paste the key. It is checked with DHL before setup
   finishes. Choose **Skip for now** instead if you do not have one yet.

### Later, or to change it

1. Open the integration and choose **Configure**.
2. Choose **Add or change a DHL API key**, paste the key, and submit. Leave the field
   blank to keep the key you already have.
3. To take the key out again, choose **Remove a DHL API key**.

Adding, changing or removing a key reloads the integration. Once a key is saved, **DHL**
appears in the courier list when you add a parcel. If you remove the key, parcels
already tracked with DHL stay in your list but stop updating, and a warning is logged,
until you add a key again.

## Tracking a DHL parcel

Choose **DHL** as the courier and enter the tracking number from your shipping email
or DHL's notification. The number is typically 10 digits for DHL Express, or letters
and numbers such as `JJD...` or `GM...` for other DHL services. Only the number goes
in, not a link.

## Limits and rules to know about

- **250 calls a day, and one call every 5 seconds.** DHL's standard key allows this and
  nothing more. Each tracked parcel costs one call each time it is updated, and a
  parcel stops being asked about once it is delivered. The integration spaces its calls
  out to stay under the rate limit, so updating several DHL parcels takes a few seconds
  each. Roughly five parcels in transit at once is about what a day's allowance covers.
  If DHL says the allowance is used up, updates pause and the last known data is kept.
- **Your own parcels only.** DHL's terms for this API apply to you. Track parcels that
  are yours.
- **Attribution.** DHL's terms ask for credit, so every entity carries the attribution
  `DHL data delivered by Deutsche Post DHL Group`.
- **30 days.** DHL removes a delivered shipment's data about 30 days after delivery, so
  a delivered DHL parcel will stop being found after that, whatever your delivered-parcel
  retention setting is.
- **Keep your key private.** It is stored in Home Assistant's config-entry storage, is
  never shown again or written to the log, and is left out of diagnostics. Do not paste
  it into forum posts or GitHub issues. If it leaks, make a new key in your DHL app and
  replace it in the integration's options.

## Troubleshooting

- **"DHL did not accept that API key":** check you copied the whole **API Key** (not the
  Secret), with no extra spaces, from an app that has **Shipment Tracking – Unified**
  ticked and has been approved.
- **"Could not reach DHL":** DHL's site may be down or blocking requests from your
  network. Try again shortly.
- **You cannot get a key:** the usual cause is an account without a company name. Add one
  to your DHL developer profile and try creating the app again.
- **A parcel shows `unknown`:** DHL has no record of that number yet (it appears once DHL
  has scanned it) or the number is wrong.
- **DHL is missing from the courier list:** no key is saved. Add one in **Configure**.
- **Status never shows "out for delivery":** DHL's answer only says
  *pre-transit / transit / delivered / failure*. DHL's own wording for the latest event
  is available as the parcel's `raw_status` attribute.
