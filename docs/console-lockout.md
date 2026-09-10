# Wall tablet console: Companion as the single app

This document maps the "Wall Tablet Console Lockout" task (Companion plus
Browser Mod plus ELK M1) onto Local MDM. That task assumed no Device Owner
lockdown and classified its own kiosk controls as cosmetic. With the DPC as
Device Owner the classification changes, and several of its workarounds are
no longer needed. What stays in Home Assistant (the console state machine,
the ELK-validated lock view, the owner override) is unchanged and out of
scope for this repository; this is only the layer under it.

## Standing policy for a wall tablet

Set once per tablet after pairing:

| Entity | Value | Why |
| --- | --- | --- |
| `text.<tablet>_kiosk_packages` | `io.homeassistant.companion.android` | Companion is the only application allowed in lock task, and the DPC becomes HOME so a reboot lands in Companion |
| `switch.<tablet>_kiosk_mode` | on | Lock task: no home, no recents, no other apps, no notification shade beyond what `setLockTaskFeatures` allows |
| `switch.<tablet>_automatic_os_updates` | on | Android installs OS updates as soon as the vendor offers them |
| `switch.<tablet>_stay_awake_on_power` | on | A wall tablet on power never times out; brightness is still Companion's to manage |
| `switch.<tablet>_status_bar_disabled` | on | No quick settings pull-down |
| `switch.<tablet>_app_installs_blocked`, `_app_uninstalls_blocked` | on | Nothing arrives or leaves except through the DPC |
| `switch.<tablet>_usb_file_transfer_blocked` | on | adb stays available; MTP does not |
| `switch.<tablet>_safe_boot_blocked`, `_factory_reset_blocked` | on | Closes the Settings path; recovery-mode wipe remains for the owner |

Event-driven policy (from the alarm panel, a camera detection, or the
console state machine) then adds `camera_disabled` and `screen_capture_disabled`
on top, and can turn kiosk off for `owner_override`.

## What changes in the task's honesty table

| Control | Task's classification | With Local MDM | Why |
| --- | --- | --- | --- |
| Leaving the app | not preventable | enforced | Lock task mode is enforced by the system for a Device Owner; home, recents, and other apps are unavailable |
| Reaching Android settings | not preventable | enforced | Settings is not in the lock task allow list and the status bar is disabled |
| Android screen pinning | partial | superseded | Lock task replaces pinning; there is no release gesture |
| Kill and relaunch the Companion app | window of exposure | closed | A reboot or a relaunch lands in `KioskHome`, which re-enters lock task before launching Companion |
| Browser Mod lock popup | cosmetic | still cosmetic, but now inside an enforced container | Bypassing the overlay still leaves the user inside Companion only |
| Non-admin tablet HA user | enforced | enforced | Unchanged; the HA permission model is still what denies |
| Code validation by ELK panel | enforced | enforced | Unchanged; the panel remains the security boundary |
| VLAN segmentation | enforced | enforced | Unchanged, and now also protects the DPC port |

Physical access with the recovery-mode wipe remains the floor, by design
(docs/security.md). adb also remains available under every policy; it is the
recovery path, and USB debugging should be disabled in developer options by
the owner once the tablet is provisioned if that exposure is unwanted.

## Companion app updates

Companion is installed from GitHub releases, not Google Play, on a tablet with
no Google account. The DPC reports the installed version in
`sensor.<tablet>_kiosk_app_version`, and the core `github` integration's
latest release sensor for `home-assistant/android` gives the newest tag. The
silent install action that closes that loop is written but not yet routed;
see docs/backlog.md for the decision that is pending.

## Provisioning order for a new wall tablet

1. Factory reset, skip accounts, enable USB debugging.
2. Install the DPC and the Companion APK (`app-full-release.apk` from the
   release matching the version you want), then `dpm set-device-owner`.
3. Open Companion once and sign in to Home Assistant as the tablet's
   non-admin user; set the console dashboard as its default.
4. Pair the DPC with Home Assistant and apply the standing policy above.
5. Reboot the tablet and confirm it comes back inside Companion with the
   `kiosk lock` sensor showing locked.
