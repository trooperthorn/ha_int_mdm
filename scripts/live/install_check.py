"""Call local_mdm.install_package for the Companion release and watch last_install."""

import json
import sys
import time

from ha_api import Ha, registry_path

ha = Ha(sys.argv[1], sys.argv[2])
url, sha = sys.argv[3], sys.argv[4]
prefix = "tablet_27bf2159_21f6_4f92_bf98_8ed9e1dc0c8d"

code, entries = ha.call("GET", "/api/config/config_entries/entry?domain=local_mdm")
code, devices = ha.call(
    "GET", "/api/states"
)  # devices are not in REST; use the service registry via websocket-free trick:
# the device id is embedded in the entity registry only; take it from a diagnostics download instead
code, diag = ha.call("GET", f"/api/diagnostics/config_entry/{entries[0]['entry_id']}")
device_id = None
for d in diag.get("home_assistant", {}).get("devices", []) if isinstance(diag, dict) else []:
    device_id = d.get("id")
if device_id is None:
    # fallback: search the device registry file
    reg = json.loads(registry_path().read_text())
    device_id = next(
        d["id"]
        for d in reg["data"]["devices"]
        if any(i[0] == "local_mdm" for i in d["identifiers"])
    )
print("device", device_id)

t0 = time.monotonic()
code, r = ha.call(
    "POST",
    "/api/services/local_mdm/install_package",
    {"device_id": device_id, "url": url, "sha256": sha},
)
print("action:", code, (r if isinstance(r, str) else "")[:120])
seen = None
while time.monotonic() - t0 < 600:
    s = ha.state(f"sensor.{prefix}_last_install")
    if s != seen:
        print(f"t+{time.monotonic() - t0:5.1f}s last_install={s}")
        seen = s
    if s in ("installed", "failed"):
        break
    time.sleep(2)
code, st = ha.call("GET", f"/api/states/sensor.{prefix}_last_install")
print("attrs:", {k: st["attributes"].get(k) for k in ("package", "message", "at")})
print("kiosk_app_version:", ha.state(f"sensor.{prefix}_kiosk_app_version"))
