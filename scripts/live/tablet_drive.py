"""Pair the Samsung tablet (via adb forward/reverse) with the test HA and run the acceptance checks."""

import sys
import time

from ha_api import Ha

ha = Ha(sys.argv[1], sys.argv[2])
step = sys.argv[3]
prefix = "tablet_4bb7f18d_31e7_4ab6_82c0_8ef986b50b3f"
E = lambda d, n: f"{d}.{prefix}_{n}"  # noqa: E731

if step == "pair":
    token = sys.argv[4]
    code, flow = ha.call("POST", "/api/config/config_entries/flow", {"handler": "local_mdm"})
    code, r = ha.call("POST", f"/api/config/config_entries/flow/{flow['flow_id']}",
                      {"host": "172.30.16.1", "port": 28485, "token": token})
    print("pair:", code, r.get("type"), r.get("title") or r.get("errors") or r.get("reason"))
    time.sleep(3)
    print("entities:", len(ha.entities(prefix)))
    for n in ("device_owner", "wi_fi", "enforcement_problem", "kiosk_lock"):
        print(f"  {n}: {ha.state(E('binary_sensor', n))}")
    for n in ("android_version", "security_patch", "battery", "last_report"):
        print(f"  {n}: {ha.state(E('sensor', n))}")

elif step == "roundtrip":
    sw, enf, rep = E("switch", "camera_disabled"), E("binary_sensor", "camera_disabled_enforced"), E("sensor", "last_report")
    ha.call("POST", "/api/services/switch/turn_off", {"entity_id": sw}); time.sleep(1)
    before = ha.state(rep)
    t0 = time.monotonic()
    ha.call("POST", "/api/services/switch/turn_on", {"entity_id": sw})
    while time.monotonic() - t0 < 5 and not (ha.state(enf) == "on" and ha.state(rep) != before):
        time.sleep(0.05)
    print(f"round trip: switch={ha.state(sw)} enforced={ha.state(enf)} new_report={ha.state(rep) != before} {1000*(time.monotonic()-t0):.0f} ms")
    ha.call("POST", "/api/services/switch/turn_off", {"entity_id": sw}); time.sleep(1.5)
    print("after off:", ha.state(sw), ha.state(enf), "problem:", ha.state(E("binary_sensor", "enforcement_problem")))

elif step == "kiosk":
    on = sys.argv[4] == "on"
    ha.call("POST", "/api/services/text/set_value", {"entity_id": E("text", "kiosk_packages"), "value": sys.argv[5] if len(sys.argv) > 5 else "com.android.settings"})
    code, r = ha.call("POST", f"/api/services/switch/turn_{'on' if on else 'off'}", {"entity_id": E("switch", "kiosk_mode")})
    for i in range(6):
        time.sleep(0.5)
    print(f"kiosk {'on' if on else 'off'}: http {code} lock_sensor={ha.state(E('binary_sensor', 'kiosk_lock'))} version={ha.state(E('sensor', 'kiosk_app_version'))}")

elif step == "status":
    for n in ("kiosk_lock", "device_owner", "os_update_pending"):
        print(f"  {n}: {ha.state(E('binary_sensor', n))}")
    print("  last_report:", ha.state(E("sensor", "last_report")))
    print("  kiosk_app_version:", ha.state(E("sensor", "kiosk_app_version")))

elif step == "flags":
    action = sys.argv[4]
    for n in ("automatic_os_updates", "stay_awake_on_power"):
        ha.call("POST", f"/api/services/switch/turn_{action}", {"entity_id": E("switch", n)}); time.sleep(0.5)
        print(f"  {n}: {ha.state(E('switch', n))} enforced={ha.state(E('binary_sensor', n + '_enforced'))}")

elif step == "install":
    import json
    reg = json.load(open("/home/sean/mdm-ha-config/.storage/core.device_registry"))
    dev = next(d["id"] for d in reg["data"]["devices"] if any(i[0] == "local_mdm" and "4bb7f18d" in i[1] for i in d["identifiers"]))
    t0 = time.monotonic()
    code, r = ha.call("POST", "/api/services/local_mdm/install_package", {"device_id": dev, "url": sys.argv[4], "sha256": sys.argv[5]})
    print("action:", code)
    seen = None
    while time.monotonic() - t0 < 900:
        s = ha.state(E("sensor", "last_install"))
        if s != seen:
            print(f"t+{time.monotonic()-t0:5.1f}s last_install={s}"); seen = s
        if s in ("installed", "failed"):
            break
        time.sleep(2)
    code, st = ha.call("GET", f"/api/states/{E('sensor', 'last_install')}")
    print("attrs:", {k: st["attributes"].get(k) for k in ("package", "message")})
