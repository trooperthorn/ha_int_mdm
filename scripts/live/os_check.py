"""Reload the entry, then drive the new switches and print the new sensors."""

import sys
import time

from ha_api import Ha

ha = Ha(sys.argv[1], sys.argv[2])
action = sys.argv[3]
prefix = "tablet_27bf2159_21f6_4f92_bf98_8ed9e1dc0c8d"

if action == "reload":
    code, entries = ha.call("GET", "/api/config/config_entries/entry?domain=local_mdm")
    entry_id = entries[0]["entry_id"]
    print("reload", ha.call("POST", f"/api/config/config_entries/entry/{entry_id}/reload")[0])
    time.sleep(3)
    for e in (
        "sensor.android_version",
        "sensor.security_patch",
        "sensor.kiosk_app_version",
        "binary_sensor.os_update_pending",
        "switch.automatic_os_updates",
        "switch.stay_awake_on_power",
    ):
        d, n = e.split(".")
        print(f"  {e}: {ha.state(f'{d}.{prefix}_{n}')}")
elif action in ("on", "off"):
    for n in ("automatic_os_updates", "stay_awake_on_power"):
        code, r = ha.call(
            "POST", f"/api/services/switch/turn_{action}", {"entity_id": f"switch.{prefix}_{n}"}
        )
        time.sleep(0.5)
        print(
            f"  {n}: http {code} -> {ha.state(f'switch.{prefix}_{n}')} "
            f"enforced={ha.state(f'binary_sensor.{prefix}_{n}_enforced')}"
        )
elif action == "kiosk":
    on = sys.argv[4] == "on"
    ha.call(
        "POST",
        "/api/services/text/set_value",
        {"entity_id": f"text.{prefix}_kiosk_packages", "value": "com.android.settings"},
    )
    code, r = ha.call(
        "POST",
        f"/api/services/switch/turn_{'on' if on else 'off'}",
        {"entity_id": f"switch.{prefix}_kiosk_mode"},
    )
    time.sleep(2)
    print(
        f"  kiosk {'on' if on else 'off'}: http {code} lock_sensor={ha.state(f'binary_sensor.{prefix}_kiosk_lock')}"
    )
elif action == "status":
    for n in ("kiosk_lock", "device_owner", "os_update_pending"):
        print(f"  {n}: {ha.state(f'binary_sensor.{prefix}_{n}')}")
    print(f"  last_report: {ha.state(f'sensor.{prefix}_last_report')}")
