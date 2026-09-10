# Security

## Trust boundaries

| Boundary | Who can cross it | Control | Enforced or advisory |
| --- | --- | --- | --- |
| LAN to tablet port 8484 | anyone on the tablet's network segment | bearer token, constant-time compare, 64 KiB body cap | enforced by the DPC |
| LAN to Home Assistant webhook | anyone on a local network | unguessable 64-hex webhook id, `local_only`, `device_id` must match the entry | enforced by Home Assistant core and the integration |
| Home Assistant operator to tablet policy | anyone who can toggle the switches | Home Assistant's own auth and permissions | enforced by core |
| Policy content | the integration, and anything else holding the token | forbidden-key guard, kiosk-needs-a-target rule | enforced on both sides |

Transport is plain HTTP. The token protects against a casual peer on the same
VLAN, not against a peer that can capture traffic. Put tablets on a segment
where the only other talker is Home Assistant, or terminate TLS in front of
both ends. TLS on the DPC is a backlog item, not a promise.

## The network brick, and why both sides check

A Device Owner can add `DISALLOW_CONFIG_WIFI` and similar restrictions. If a
policy did that while the tablet was on the wrong network, the DPC could no
longer be reached to lift the restriction, and the user could not change
networks by hand. With `DISALLOW_DEBUGGING_FEATURES` also set, adb is gone
too, and a factory wipe is the only path back.

The integration refuses those keys in `policy.py` before building a request.
The DPC refuses the same keys in `Policy.kt` before touching
`DevicePolicyManager`. Two independent checks mean a bug or a bypass on one
side (a template calling the tablet directly, a future version of the
integration that forgets) still cannot brick a tablet. The DPC never disables
adb under any policy; that is the documented recovery path.

`factory_reset_blocked` is offered because it only blocks the Settings menu
path. The recovery-mode wipe still works, so the tablet is always recoverable
by someone with physical access, which is the intended floor.

## What this is not

- Not a defense against a hostile Home Assistant. Anyone who can call the
  switches can restrict the tablet within the allowed set.
- Not tamper evidence. The DPC keeps no audit log; Home Assistant's recorder
  history of the switches and enforced sensors is the record.
- Not a sandbox. A malicious app already on the tablet is out of scope; Device
  Owner mode with `install_apps_blocked` limits what arrives after
  provisioning.
- Not root. The DPC uses only public Device Owner APIs, so Knox attestation
  and the hardware keystore stay intact.

## Secrets in this repository

None. The pairing token exists only on the tablet and in the Home Assistant
config entry (redacted in diagnostics). Release signing for the APK is the
operator's own key.
