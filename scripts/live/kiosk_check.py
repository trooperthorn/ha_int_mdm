import sys
import time

from ha_api import Ha

ha = Ha(sys.argv[1], sys.argv[2])
mdm = ha.entities("tablet_27bf2159")
kiosk_switch = next(e for e in mdm if e.startswith("switch.") and e.endswith("_kiosk_mode"))
kiosk_lock = next(e for e in mdm if e.endswith("_kiosk_lock"))
kiosk_enf = next(e for e in mdm if e.endswith("kiosk_mode_enforced"))
action = sys.argv[3]
code, r = ha.call("POST", f"/api/services/switch/turn_{action}", {"entity_id": kiosk_switch})
print("service", code)
for i in range(8):
    time.sleep(0.5)
    print(
        f"t+{(i + 1) * 0.5:.1f}s switch={ha.state(kiosk_switch)} lock_sensor={ha.state(kiosk_lock)} enforced={ha.state(kiosk_enf)}"
    )
