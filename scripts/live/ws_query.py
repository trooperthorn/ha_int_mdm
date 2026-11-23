"""Run one websocket command against a Home Assistant instance.

Usage: ws_query.py '<json command without id>'

LOCAL_MDM_HA_URL is the instance (default http://127.0.0.1:8123) and
LOCAL_MDM_HA_TOKEN_FILE a file holding a long-lived access token.
"""

import asyncio
import json
import os
import pathlib
import sys

import aiohttp

BASE = os.environ.get("LOCAL_MDM_HA_URL", "http://127.0.0.1:8123").rstrip("/")
TOKEN = pathlib.Path(os.environ["LOCAL_MDM_HA_TOKEN_FILE"]).read_text().strip()


async def main():
    cmd = json.loads(sys.argv[1])
    async with (
        aiohttp.ClientSession() as session,
        session.ws_connect(f"{BASE}/api/websocket", max_msg_size=64 * 1024 * 1024) as ws,
    ):
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": TOKEN})
        assert (await ws.receive_json())["type"] == "auth_ok"
        cmd["id"] = 1
        await ws.send_json(cmd)
        reply = await ws.receive_json()
        print(json.dumps(reply.get("result", reply)))


asyncio.run(main())
