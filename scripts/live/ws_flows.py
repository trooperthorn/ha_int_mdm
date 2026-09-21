"""List config flows in progress over the websocket API (the REST index is gone)."""

import asyncio
import json
import sys

import aiohttp

from ha_api import Ha


async def main():
    ha = Ha(sys.argv[1], sys.argv[2])
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect("http://127.0.0.1:8123/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": ha.token})
            assert (await ws.receive_json())["type"] == "auth_ok"
            await ws.send_json({"id": 1, "type": "config_entries/flow/progress"})
            reply = await ws.receive_json()
            print(json.dumps([{k: f.get(k) for k in ("flow_id", "handler", "step_id", "context")} for f in reply["result"]]))


asyncio.run(main())
