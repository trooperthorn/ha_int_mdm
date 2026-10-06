"""Drive a fresh Home Assistant through onboarding, the Local MDM config flow,
and the acceptance round trip, using only the REST API. Local test instance only."""

import json
import secrets
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8123"
DPC_HOST, DPC_PORT, DPC_TOKEN = sys.argv[1], int(sys.argv[2]), sys.argv[3]
CLIENT_ID = "http://127.0.0.1:8123/"
TOKEN = None


def call(method, path, body=None, auth=True, form=None):
    data = None
    headers = {}
    if form is not None:
        data = form.encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def state(entity_id):
    code, s = call("GET", f"/api/states/{entity_id}")
    return s["state"] if code == 200 else f"http{code}"


# 1. onboarding
code, steps = call("GET", "/api/onboarding", auth=False)
if any(s["step"] == "user" and not s["done"] for s in steps):
    password = secrets.token_urlsafe(16)
    code, r = call(
        "POST",
        "/api/onboarding/users",
        {
            "client_id": CLIENT_ID,
            "name": "MDM Tester",
            "username": "mdmtester",
            "password": password,
            "language": "en",
        },
        auth=False,
    )
    assert code == 200, r
    code, tok = call(
        "POST",
        "/auth/token",
        auth=False,
        form=f"grant_type=authorization_code&code={r['auth_code']}&client_id={CLIENT_ID}",
    )
    assert code == 200, tok
    TOKEN = tok["access_token"]
    print("onboarded user mdmtester, password:", password)
    for path, body in (
        ("/api/onboarding/core_config", {}),
        ("/api/onboarding/analytics", {}),
        ("/api/onboarding/integration", {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID}),
    ):
        code, r = call("POST", path, body)
        print("  ", path, code)
        if path.endswith("integration") and code == 200:
            code, tok = call(
                "POST",
                "/auth/token",
                auth=False,
                form=f"grant_type=authorization_code&code={r['auth_code']}&client_id={CLIENT_ID}",
            )
            TOKEN = tok["access_token"]
else:
    print("already onboarded; pass a token as argv[4]")
    TOKEN = sys.argv[4]

# 2. config flow
code, flow = call("POST", "/api/config/config_entries/flow", {"handler": "local_mdm"})
assert code == 200, flow
print("flow step:", flow["step_id"], "schema keys:", [f["name"] for f in flow["data_schema"]])
code, result = call(
    "POST",
    f"/api/config/config_entries/flow/{flow['flow_id']}",
    {"host": DPC_HOST, "port": DPC_PORT, "token": DPC_TOKEN},
)
print(
    "flow result:",
    code,
    result.get("type"),
    result.get("title") or result.get("errors") or result.get("reason"),
)
assert result.get("type") == "create_entry", result
entry_id = result["result"]["entry_id"]

# 3. entities
time.sleep(2)
code, states = call("GET", "/api/states")
mdm = sorted(s["entity_id"] for s in states if "tablet_27bf2159" in s["entity_id"])
print(f"{len(mdm)} entities; sample:", mdm[:4])
cam_switch = next(e for e in mdm if e.endswith("_camera_disabled") and e.startswith("switch."))
cam_enf = next(e for e in mdm if e.endswith("camera_disabled_enforced"))
last_report = next(e for e in mdm if e.endswith("_last_report"))
problem = next(e for e in mdm if e.endswith("enforcement_problem"))
print(
    "device_owner:",
    state(next(e for e in mdm if e.endswith("_device_owner"))),
    "wifi:",
    state(next(e for e in mdm if e.endswith("_wi_fi"))),
    "problem:",
    state(problem),
    "last_report:",
    state(last_report),
)

# make sure we start from off
call("POST", "/api/services/switch/turn_off", {"entity_id": cam_switch})
time.sleep(1)
before_report = state(last_report)
print("start:", cam_switch, state(cam_switch), cam_enf, state(cam_enf))

# 4. the acceptance test: input_boolean -> automation -> switch -> DPC -> webhook -> sensor
t0 = time.monotonic()
call(
    "POST",
    "/api/services/input_boolean/turn_on",
    {"entity_id": "input_boolean.tablet_camera_lockdown"},
)
deadline = t0 + 5
while time.monotonic() < deadline:
    if state(cam_enf) == "on" and state(last_report) != before_report:
        break
    time.sleep(0.05)
elapsed = time.monotonic() - t0
print(
    f"round trip: switch={state(cam_switch)} enforced={state(cam_enf)} "
    f"new_report={state(last_report) != before_report} elapsed={elapsed * 1000:.0f} ms"
)

# switch attributes prove the DPC's answer, not just the webhook
code, s = call("GET", f"/api/states/{cam_switch}")
print(
    "switch attrs:",
    {k: s["attributes"].get(k) for k in ("enforcement", "reported_value", "policy_version")},
)

# 5. turn back off and confirm
call(
    "POST",
    "/api/services/input_boolean/turn_off",
    {"entity_id": "input_boolean.tablet_camera_lockdown"},
)
time.sleep(1.5)
print("after off:", state(cam_switch), state(cam_enf), "problem:", state(problem))

# 6. kiosk via text entity then switch
kiosk_text = next(e for e in mdm if e.startswith("text.") and e.endswith("kiosk_packages"))
kiosk_switch = next(e for e in mdm if e.startswith("switch.") and e.endswith("_kiosk_mode"))
kiosk_lock = next(e for e in mdm if e.endswith("_kiosk_lock"))
code, r = call("POST", "/api/services/switch/turn_on", {"entity_id": kiosk_switch})
print("kiosk with no packages:", code, (r if isinstance(r, str) else "")[:120])
call(
    "POST",
    "/api/services/text/set_value",
    {"entity_id": kiosk_text, "value": "com.android.settings"},
)
time.sleep(0.5)
code, r = call("POST", "/api/services/switch/turn_on", {"entity_id": kiosk_switch})
time.sleep(1.5)
print(
    "kiosk on:",
    code,
    "switch",
    state(kiosk_switch),
    "lock sensor",
    state(kiosk_lock),
    "text",
    state(kiosk_text),
)
call("POST", "/api/services/switch/turn_off", {"entity_id": kiosk_switch})
time.sleep(1.5)
print("kiosk off:", state(kiosk_switch), "lock sensor", state(kiosk_lock))
print("entry_id", entry_id, "token", TOKEN[:12] + "...")
