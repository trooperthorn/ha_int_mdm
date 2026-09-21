"""Tiny REST helper for the local WSL test instance: login with username/password."""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8123"
CLIENT_ID = "http://127.0.0.1:8123/"


class Ha:
    def __init__(self, username, password):
        self.token = None
        code, flow = self.call("POST", "/auth/login_flow", {"client_id": CLIENT_ID, "handler": ["homeassistant", None], "redirect_uri": CLIENT_ID})
        assert code == 200, flow
        code, r = self.call("POST", f"/auth/login_flow/{flow['flow_id']}", {"client_id": CLIENT_ID, "username": username, "password": password})
        assert code == 200 and r.get("type") == "create_entry", r
        code, tok = self.call("POST", "/auth/token", form=f"grant_type=authorization_code&code={r['result']}&client_id={CLIENT_ID}")
        assert code == 200, tok
        self.token = tok["access_token"]

    def call(self, method, path, body=None, form=None):
        data, headers = None, {}
        if form is not None:
            data, headers["Content-Type"] = form.encode(), "application/x-www-form-urlencoded"
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:400]

    def state(self, entity_id):
        code, s = self.call("GET", f"/api/states/{entity_id}")
        return s["state"] if code == 200 else f"http{code}"

    def entities(self, needle):
        return sorted(s["entity_id"] for s in self.call("GET", "/api/states")[1] if needle in s["entity_id"])


if __name__ == "__main__":
    ha = Ha(sys.argv[1], sys.argv[2])
    print(ha.token)
