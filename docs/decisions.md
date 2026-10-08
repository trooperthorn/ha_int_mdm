# Decisions

## 2026-10-08: Minimum Home Assistant is 2026.10.0, schemas use probatio

Core 2026.10 types flow, service and websocket schemas as probatio, so the
voluptuous schemas failed mypy (developer blog 2026-09-30, "Probatio is our
validation engine"). The integration now imports `probatio` directly, as core
does; runtime behavior is unchanged because core has validated with probatio
since 2026.9. The suite runs on core 2026.10.0 and `hacs.json` follows the
tested core. CodeQL init and analyze move to v4.38.2 together and Dependabot
now groups them. Rejected: aliasing `probatio as vol`, which core's lint config
bans.

## 2026-09-10: custom DPC over the Android Management API

Rejected: a backend built on Google's Android Management API. It requires
enrollment through Google's cloud and every policy transits it, which breaks
the local-only requirement and adds latency that an alarm-driven lockdown
cannot afford. Chosen: a Device Owner app provisioned over adb with an HTTP
endpoint on the LAN.

## 2026-09-10: one full policy document per push, not per-key calls

Rejected: a `PUT /v1/policy/<key>` per switch. Chosen: the whole document
every time, with a version. The DPC re-applies every key so a lost earlier
push cannot leave the tablet in a mixed state, and the guard can reason about
the document as a whole (kiosk needs packages).

## 2026-09-10: the tablet is the source of truth on restart

Rejected: storing the desired policy in the config entry. Chosen: read the
tablet's applied policy at setup. A Home Assistant restore from backup must
not push a stale policy, and a tablet that was changed by hand over adb should
be shown as it is.

## 2026-09-10: forbidden keys are refused even with a false value

Rejected: allowing `no_config_wifi: false` as a harmless no-op. Chosen: reject
the document. A key that is never accepted cannot become accepted by a typo in
a value, and neither side needs a per-value rule.

## 2026-09-10: `factory_reset_blocked` is offered

The restriction only removes the Settings path; recovery-mode wipe remains.
The tablet stays recoverable with physical access, so this does not meet the
network-brick definition. Documented in security.md.

## 2026-09-10: scanner finding `update-listener-plus-reload` is not applicable

`config_flow.py` uses `async_update_reload_and_abort` in the reauth step and
the entry has no update listener; the options flow is `OptionsFlowWithReload`.
The 2026-05-07 developer post's error condition (listener plus reload in flow)
does not arise.

## 2026-09-10: domain `local_mdm`, repository `ha_int_mdm`

`mdm` alone is generic enough to collide with a future core integration; the
`local_` prefix states the design goal. The repository keeps the `ha_int_`
convention even though it also carries the Android app, because HACS only
sees the integration.

## 2026-09-10: AGP 9.4.0 on Gradle 9.7.1, no Kotlin plugin

Rejected: AGP 8.13.2 with the Kotlin Android plugin. Gradle 9.6 removed the
internal `InternalProblems` API that every AGP 8.x release calls, and the
current Gradle is 9.7.1. Chosen: AGP 9.4.0, which ships built-in Kotlin, so
`org.jetbrains.kotlin.android` is not declared. The JDK 25 bundled with
Android Studio runs Gradle 9.7.1; Gradle 8.10.2 refused it.

## 2026-09-10: NanoHTTPD 422 is a private IStatus

NanoHTTPD 2.3.1 has no 422 constant in `Response.Status`; the server defines
a private `IStatus` for it rather than misusing 400, because the integration
distinguishes "unsafe or refused" (422) from "malformed" (400).

## 2026-09-10: the kiosk activity requests a settled report

Rejected: reporting lock task state from the policy PUT response alone.
`startLockTask` returns before the system has switched modes, so the response
and the immediate report both said "not locked". Chosen: `KioskActivity`
sends `ACTION_REPORT` to the service after starting or stopping lock task, and
the service reports 750 ms later. Home Assistant's kiosk lock sensor now
follows within a second instead of at the next heartbeat.

## 2026-09-10: OS updates through SystemUpdatePolicy, not a custom updater

Rejected: polling the OEM for OTA packages and calling `installSystemUpdate`.
Chosen: `createAutomaticInstallPolicy()`, which tells Android to install a
system update as soon as the OEM's updater offers it, with no user prompt.
The tablet can only update as fast as its vendor ships; the DPC cannot make
Samsung publish sooner. `getPendingSystemUpdate` is reported so Home Assistant
can see that an update was received and is waiting on the automatic install.

## 2026-09-10: kiosk HOME through an activity-alias

Rejected: a static HOME intent filter on `KioskActivity`. It made the DPC
answer HOME even after kiosk was turned off, so the launcher never came back.
Chosen: an `activity-alias` (`KioskHome`) that the engine enables only while
kiosk is on and registers as the persistent preferred HOME activity. Verified
with `cmd package resolve-activity` in both states.

## 2026-09-10: app updates by signature continuity, sha256 optional

Android refuses to update an installed package with an APK signed by a
different key, so a Device Owner install from a URL cannot replace Companion
with a look-alike. The optional sha256 (GitHub publishes one per asset) adds
transport integrity only. Wired on 2026-09-11 at the owner's request and verified with the Companion
release on the emulator.

## 2026-09-11: package visibility through `<queries>`, not QUERY_ALL_PACKAGES

Rejected: `QUERY_ALL_PACKAGES`. Chosen: a `<queries>` element for the
MAIN/LAUNCHER intent, which is exactly the set the DPC needs (apps it can
put in kiosk and report versions for).

## 2026-09-11: the shell package is always in the lock task allow list

On a Galaxy Tab A11+ the "Allow USB debugging?" dialog never appeared inside
kiosk, because it is an activity of `com.android.shell` and lock task blocks
activities from packages outside the allow list. adb is the documented
recovery path, so the DPC now adds the shell package unconditionally.

## 2026-09-11: Wi-Fi provisioning adds, never switches

`enableNetwork(id, true)` tells Android to disable every other network and
try the new one now; on the Samsung that took the tablet off the LAN for a
few seconds and, with a wrong password, would have stranded it. The DPC
passes `false` and lets Android pick the new network when the current one is
gone. The password is handed to Android and not retained.

## 2026-09-11: a reboot action

Rejected: relying on adb to reboot a tablet during qualification. Chosen:
`DevicePolicyManager.reboot`, exposed as a Home Assistant button, because
the whole point of the design is that adb is a recovery path, not a control
path.

## 2026-09-11: the connected SSID is cached while Wi-Fi stays connected

One UI returned the SSID from `connectionInfo` on roughly one call in three
even with the location permission granted and location on. The DPC keeps the
last good value while the transport is still Wi-Fi and clears it when the
connection drops, so Home Assistant's Wi-Fi network sensor no longer flickers
to unknown between heartbeats.

## 2026-09-29: UniFi Network as the address book

Rejected for now: zeroconf announcements from the DPC (the tablet VLAN
needs an mDNS reflector) and a pairing code on the tablet screen (a protocol
change on both sides). Chosen: each tablet is a UniFi client with a fixed
IP and a `Room-Tab` name, and the integration reads the UniFi Network
integration's client trackers. The config flow offers connected, unpaired
`Room-Tab` clients, and the coordinator follows a tablet whose address
changed by looking its MAC up in UniFi. A new address is adopted only when
the tablet there accepts the stored token and reports the entry's device
id, so a stale or spoofed tracker cannot redirect the entry. Area matching
never creates an area.

## 2026-09-29: the policy is unknown until the tablet answers

Found on the live fleet: a Home Assistant start with the tablets asleep put
every entry in setup retry (the webhook PUT raised `ConfigEntryNotReady`,
undoing the intent of the unreachable-is-data change), and the placeholder
policy of an unreachable tablet would have been re-pushed as drift the
moment it came back, turning its policies off. Chosen: the webhook URL is
kept and resent on the tablet's next answer; the desired policy is taken
from the tablet's first report after setup; drift reconciliation and every
switch write wait for that, and a write while it is still unknown is
refused with an error rather than built on the placeholder.
