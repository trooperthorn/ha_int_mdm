# Decisions

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
