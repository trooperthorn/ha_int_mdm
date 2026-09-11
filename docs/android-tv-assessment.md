# Sony Bravia (Google TV) assessment

Assessed 2026-09-11 from vendor and MDM-vendor documentation plus what Home
Assistant already knows about the sets. Nothing was changed on any TV.

## The sets

| HA name | Model | Platform | Notes |
| --- | --- | --- | --- |
| Great Room Sony | XR-77A80J (2021) | Google TV, Android TV OS 10 at launch, updated since | Android TV Remote pairing exists |
| Kitchen TV | KD-55X85K (2022) | Google TV, Android TV OS 10/11 at launch, updated since | Android TV Remote pairing exists; adb port 5555 closed, remote 6466 and cast 8009 open |
| Master TV | unknown | Android TV Remote only | model not in the registry |

## Can a Bravia be a Device Owner?

Yes in principle. Google TV is Android TV OS, which carries the same
`DevicePolicyManager`; commercial MDMs (Hexnode, Scalefusion) enrol Android
TV sets with the same `adb shell dpm set-device-owner` path this project
uses, and their kiosk mode on TV is lock task. The preconditions are the
usual ones, and on a TV they cost more than on a tablet:

- **No accounts on the device.** The Google account must be removed
  (Settings > Accounts, or a factory reset with sign-in skipped). Without it
  the Play Store, Assistant, YouTube sign-in and the Google TV home feed are
  gone; Cast receiver still works, Sony's own apps still work, sideloaded
  apps work. This is a living-room TV, so the trade-off is the whole
  question.
- **adb reachable.** Bravia has no usable USB debugging; it is Developer
  options > Network debugging, then `adb connect <ip>:5555`, with the
  on-screen authorisation. The port is closed on the Kitchen TV today, so
  nothing has been enabled yet.
- **Reversal is a factory reset**, as on every Device Owner device.

## What Local MDM would need

- A leanback entry: the `KioskHome` alias needs
  `android.intent.category.LEANBACK_LAUNCHER` beside HOME, and the manifest
  needs `uses-feature android.hardware.touchscreen required=false` and
  `android.software.leanback required=false`.
- D-pad focus in `KioskActivity` (the splash has no focusable views; fine)
  and in `MainActivity` (pairing token screen must be navigable by remote).
- Kiosk target: the Companion app has an Android TV build but it is a
  reduced client; a Bravia locked to it shows dashboards, not a TV.
- Wi-Fi provisioning is moot (wired) or the same code (wireless).
- `SystemUpdatePolicy`: Sony's updater is its own agent, expect the same
  "installs what it downloaded, on its schedule" behaviour as One UI.
- Screen sensors: `stay_awake_on_power` maps to nothing useful on a TV;
  power is HDMI-CEC or the Android TV Remote integration, which HA has.

## What Sean would gain

Lock task to one app, silent APK install, blocked installs and factory
reset, camera and screenshot policy (mostly moot), an enforcement sensor set
in HA. Everything else HA already does for these sets through Android TV
Remote and Cast (power, input, launch app, volume).

## Recommendation

Do not enrol the living-room sets; losing the Google account on a family
TV buys little that the Android TV Remote integration does not already
give. If one Bravia is meant to become a dedicated wall display, it is a
reasonable phase: enable Network debugging, remove the account, set Device
Owner, and qualify the leanback changes above on it first.

Sources: Hexnode "Android TV OS management with MDM", Scalefusion "Managing
Android TV box with MDM", Android developers "Lock task mode", Sony support
"Add or remove a Google account on a Google TV / Android TV", the androidtv
library "ADB setup" page.
