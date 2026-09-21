# Live drive harness

Ad-hoc scripts used to drive a real Home Assistant instance while qualifying
the integration and the DPC against hardware. They back the results recorded
in [`docs/live_qualification.md`](../../docs/live_qualification.md).

These are **not** part of the integration and are **not** run by CI. They talk
to a live instance over REST and websocket and assume a throwaway test HA
(the WSL instance at `http://127.0.0.1:8123`), not production.

| Script | Purpose |
|---|---|
| `ha_api.py` | Minimal REST helper: login flow, token exchange, authed calls |
| `ws_query.py` / `ws_flows.py` | Websocket queries and config-flow stepping |
| `drive_ha.py` | Drives onboarding and integration setup end to end |
| `tablet_drive.py` | Drives a paired tablet through policy changes |
| `install_check.py` / `kiosk_check.py` / `os_check.py` | Assert app install, kiosk and OS state |
| `states.py` | Dumps and filters entity state for a device prefix |

Credentials are passed in as arguments — nothing is hardcoded. The device-id
prefixes in `install_check.py`, `os_check.py` and `tablet_drive.py` refer to
specific test tablets and need changing for other hardware.
