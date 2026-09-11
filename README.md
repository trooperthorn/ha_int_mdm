# Local MDM for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_mdm?style=for-the-badge)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)
![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.9.0-blue.svg?style=for-the-badge)

A self-hosted Mobile Device Management pair for Android tablets: a Home
Assistant custom integration is the control plane, and a custom Device Policy
Controller (DPC) app on the tablet is the enforcer. No Google infrastructure,
no cloud round trip, no root. Policies are Home Assistant switches, so an
automation can lock a tablet down the moment an alarm panel arms or a camera
sees an unknown vehicle.

Installation, entity reference, and the acceptance test are below. Design,
protocol, security, and operations detail live in [docs/README.md](docs/README.md).

## What you get

One device per tablet with:

- Twelve policy switches (kiosk mode, camera, screen capture, status bar, app
  install and uninstall, USB file transfer, volume, safe boot, factory reset,
  automatic OS updates, stay awake on power). The switch is the desired state.
- One "enforced" binary sensor per policy, on only when the tablet reports the
  policy applied. This is the round-trip proof the switch alone cannot give.
- Status sensors: Device Owner, kiosk lock, enforcement problem, Wi-Fi,
  battery, charging, OS update pending, Android version, security patch,
  kiosk app version, policy version, DPC version, last report.
- Buttons: lock screen now, refresh. A text entity holds the kiosk package list.
- Action `local_mdm.install_package`: silent APK install from a URL, for
  keeping the Companion app current from GitHub releases.

The tablet pushes every change to a Home Assistant webhook immediately; polling
(default 60 s) only catches a missed push.

## What it will never do

The integration and the DPC both refuse any policy key that could sever Wi-Fi
or adb. A Device Owner tablet that loses its network with those settings locked
cannot receive the policy that would fix it and needs a factory wipe. The
refused list is in `custom_components/local_mdm/policy.py` and mirrored in
`android/app/src/main/java/com/trooperthorn/localmdm/Policy.kt`; both are
tested. Kiosk mode also refuses to start with no target application.

## Installation

### Tablet

1. Build and install the DPC from `android/` (see [android/README.md](android/README.md)).
   The tablet must be freshly reset with no Google account added.
2. Make it Device Owner over adb:

```bash
adb shell dpm set-device-owner com.trooperthorn.localmdm/.MdmDeviceAdminReceiver
```

3. Open Local MDM on the tablet. It shows "Device Owner: active", the tablet's
   address, port 8484, and a pairing token.

### Home Assistant

1. Add this repository to HACS as a custom integration repository, or copy
   `custom_components/local_mdm` into your config directory.
2. Restart Home Assistant.
3. Settings, Devices & services, Add integration, "Local MDM". Enter the
   address, port, and token from the tablet.

The integration registers a local-only webhook and tells the tablet its URL.
If your Home Assistant internal URL is not reachable from the tablet, set it
under Settings, System, Network before adding the tablet.

## The acceptance test

Create an input boolean and this automation, then toggle the boolean and
watch `binary_sensor.<tablet>_camera_disabled_enforced` follow:

```yaml
automation:
  - alias: Tablet camera follows helper
    triggers:
      - trigger: state
        entity_id: input_boolean.tablet_camera_lockdown
    actions:
      - action: switch.turn_{{ 'on' if trigger.to_state.state == 'on' else 'off' }}
        target:
          entity_id: switch.tablet_kitchen_camera_disabled
```

Timing: the switch call blocks until the DPC has applied the policy and
answered; the DPC then POSTs its report. In the mocked test suite the whole
path completes well under the two-second target
(`tests/test_round_trip.py`). On hardware, read the `last_report` sensor and
the Home Assistant log at debug level for `custom_components.local_mdm`; on
the tablet, `adb logcat -s LocalMdm.Policy LocalMdm.Http LocalMdm.Webhook`.

## Example: lock down when the alarm arms

```yaml
automation:
  - alias: Tablets follow the alarm
    triggers:
      - trigger: state
        entity_id: alarm_control_panel.elk_m1_house
    actions:
      - action: switch.turn_{{ 'on' if trigger.to_state.state != 'disarmed' else 'off' }}
        target:
          entity_id:
            - switch.tablet_kitchen_kiosk_mode
            - switch.tablet_kitchen_camera_disabled
```

Kiosk mode needs a target application. Set `text.tablet_kitchen_kiosk_packages`
to a comma-separated list of package names first (for example
`io.homeassistant.companion.android`); with no packages the kiosk switch
refuses to turn on, which is the safe failure. While kiosk is on the DPC is
also the HOME app, so a reboot or a home press lands back in the first
package under lock task.

## Wall tablet with the Companion app

The intended shape for a dedicated console: Companion as the only app,
OS updates installed as soon as the vendor offers them, screen always on
while powered. The standing policy, the provisioning order, and how this
changes the enforced-versus-cosmetic table of a Companion-only design are in
[docs/console-lockout.md](docs/console-lockout.md).

## Removing the integration

Turn every policy switch off first so the tablet is left unrestricted, then
remove the device from Settings, Devices & services. To remove Device Owner
from the tablet, factory reset it; Android provides no other path for an app
that is Device Owner without a Google account.

## Known limitations

- Plain HTTP with a bearer token on the LAN. Segment the tablet VLAN; see
  docs/security.md.
- The Android app is qualified on an Android 15 emulator (Device Owner,
  full round trip, reboot persistence) and as a plain app on an Android 16
  phone. A Samsung tablet and Android 14 are not yet observed; see
  docs/live_qualification.md.
- One entry per tablet; no discovery yet.
