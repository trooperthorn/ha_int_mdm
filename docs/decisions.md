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
