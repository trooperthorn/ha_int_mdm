"""The client against a real aiohttp server that mimics the DPC."""

from __future__ import annotations

import json
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from custom_components.local_mdm.api import (
    DeviceStatus,
    LocalMdmAuthError,
    LocalMdmClient,
    LocalMdmConnectionError,
    LocalMdmPolicyRefusedError,
)
from custom_components.local_mdm.policy import UnsafePolicyError

from .conftest import TOKEN, status_payload


class FakeDpc:
    """Records requests and answers like the Android DPC."""

    def __init__(self) -> None:
        self.received: list[tuple[str, str, Any]] = []
        self.status = status_payload()
        self.refuse_policy = False
        self.bad_body = False

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.auth])
        app.router.add_get("/v1/status", self.get_status)
        app.router.add_put("/v1/policy", self.put_policy)
        app.router.add_put("/v1/webhook", self.put_webhook)
        app.router.add_post("/v1/actions/lock_screen", self.lock)
        app.router.add_post("/v1/actions/install_package", self.install)
        app.router.add_post("/v1/actions/configure_wifi", self.install)
        app.router.add_post("/v1/actions/reboot", self.lock)
        return app

    @web.middleware
    async def auth(self, request: web.Request, handler):  # type: ignore[no-untyped-def]
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return web.Response(status=401)
        return await handler(request)

    async def get_status(self, request: web.Request) -> web.Response:
        self.received.append(("GET", request.path, None))
        if self.bad_body:
            return web.Response(text="[]", content_type="application/json")
        return web.json_response(self.status)

    async def put_policy(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.received.append(("PUT", request.path, body))
        if self.refuse_policy:
            return web.Response(status=422, text="kiosk needs packages")
        self.status["policy"] = body["policy"]
        self.status["policy_version"] = body["version"]
        return web.json_response(self.status)

    async def put_webhook(self, request: web.Request) -> web.Response:
        self.received.append(("PUT", request.path, await request.json()))
        return web.json_response({"ok": True})

    async def install(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.received.append(("POST", request.path, body))
        return web.json_response({"ok": True}, status=202)

    async def lock(self, request: web.Request) -> web.Response:
        self.received.append(("POST", request.path, None))
        return web.json_response({"ok": True})


@pytest.fixture
async def dpc(socket_enabled):
    fake = FakeDpc()
    server = TestServer(fake.app())
    client = TestClient(server)
    await client.start_server()
    yield fake, client
    await client.close()


def _client(client: TestClient, token: str = TOKEN) -> LocalMdmClient:
    return LocalMdmClient(client.session, client.host, client.port, token)


async def test_status_round_trip(dpc):
    fake, http = dpc
    status = await _client(http).async_get_status()
    assert isinstance(status, DeviceStatus)
    assert status.device_id == "tablet-kitchen"
    assert status.battery_level == 87
    assert status.enforcement_failures == []
    assert fake.received == [("GET", "/v1/status", None)]


async def test_bad_token_is_auth_error(dpc):
    _, http = dpc
    with pytest.raises(LocalMdmAuthError):
        await _client(http, "wrong").async_get_status()


async def test_set_policy_sends_normalized_document(dpc):
    fake, http = dpc
    status = await _client(http).async_set_policy({"camera_disabled": True}, 7)
    _, _, body = fake.received[-1]
    assert body["version"] == 7
    assert body["policy"]["camera_disabled"] is True
    assert body["policy"]["kiosk_mode"] is False
    assert status.policy_version == 7


async def test_unsafe_policy_never_reaches_the_wire(dpc):
    fake, http = dpc
    with pytest.raises(UnsafePolicyError):
        await _client(http).async_set_policy({"no_config_wifi": True}, 1)
    assert fake.received == []


async def test_dpc_refusal_is_typed(dpc):
    fake, http = dpc
    fake.refuse_policy = True
    with pytest.raises(LocalMdmPolicyRefusedError, match="kiosk needs packages"):
        await _client(http).async_set_policy({"camera_disabled": True}, 1)


async def test_webhook_and_lock(dpc):
    fake, http = dpc
    client = _client(http)
    await client.async_set_webhook("http://ha.local:8123/api/webhook/abc")
    await client.async_lock_screen()
    await client.async_reboot()
    assert fake.received[2] == ("POST", "/v1/actions/reboot", None)
    assert fake.received[0] == (
        "PUT",
        "/v1/webhook",
        {"url": "http://ha.local:8123/api/webhook/abc"},
    )
    assert fake.received[1] == ("POST", "/v1/actions/lock_screen", None)


async def test_non_object_body_is_connection_error(dpc):
    fake, http = dpc
    fake.bad_body = True
    with pytest.raises(LocalMdmConnectionError):
        await _client(http).async_get_status()


async def test_unreachable_host_is_connection_error(dpc):
    _, http = dpc
    client = LocalMdmClient(http.session, "127.0.0.1", 1, TOKEN, timeout=0.5)
    with pytest.raises(LocalMdmConnectionError):
        await client.async_get_status()


def test_malformed_payload():
    with pytest.raises(ValueError):
        DeviceStatus.from_payload({"policy": {}})
    with pytest.raises(ValueError):
        DeviceStatus.from_payload(json.loads('{"device_id": "x", "policy_version": "abc"}'))


async def test_install_package_normalizes_digest(dpc):
    fake, http = dpc
    await _client(http).async_install_package(
        "https://example.invalid/app.apk", "SHA256:" + "A" * 64
    )
    assert fake.received[-1] == (
        "POST",
        "/v1/actions/install_package",
        {"url": "https://example.invalid/app.apk", "sha256": "a" * 64},
    )
    await _client(http).async_install_package("https://example.invalid/app.apk")
    assert fake.received[-1][2] == {"url": "https://example.invalid/app.apk"}


async def test_configure_wifi_omits_empty_password(dpc):
    fake, http = dpc
    await _client(http).async_configure_wifi("Net", None, True)
    assert fake.received[-1] == (
        "POST",
        "/v1/actions/configure_wifi",
        {"ssid": "Net", "hidden": True},
    )
