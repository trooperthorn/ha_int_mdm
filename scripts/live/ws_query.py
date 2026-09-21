"""Run one websocket command against El Rancho Assist with the token file. Usage: ws_query.py '<json command without id>'"""

import asyncio
import json
import sys

import aiohttp

TOKEN = open("/mnt/c/Users/sean.LAB/workspace/el-rancho.token").read().strip()
URL = "http://192.168.30.3:8123/api/websocket"


async def main():
    cmd = json.loads(sys.argv[1])
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(URL, max_msg_size=64 * 1024 * 1024) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            assert (await ws.receive_json())["type"] == "auth_ok"
            cmd["id"] = 1
            await ws.send_json(cmd)
            reply = await ws.receive_json()
            print(json.dumps(reply.get("result", reply)))


asyncio.run(main())
