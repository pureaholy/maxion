"""Профили устройства и их влияние на SESSION_INIT."""

from __future__ import annotations

import pytest

from maxion.raw import Device, MaxClient
from maxion.raw.enums import DeviceType
from maxion.raw.errors import AuthError
from maxion.raw.opcodes import Opcode
from tests.test_client import FakeTransport


def test_web_profile_has_no_phone_auth():
    device = Device.web()
    assert device.device_type is DeviceType.WEB
    assert device.supports_phone_auth is False
    assert device.session_extras() == {}


@pytest.mark.parametrize("factory", [Device.android, Device.ios])
def test_phone_profiles_support_phone_auth(factory):
    device = factory()
    assert device.supports_phone_auth is True
    assert device.is_mobile is True
    extras = device.session_extras()
    assert set(extras) == {"client_session_id", "instance_id"}
    assert isinstance(extras["client_session_id"], int)


def test_desktop_is_not_mobile_but_allows_phone_auth():
    device = Device.desktop()
    assert device.is_mobile is False
    assert device.supports_phone_auth is True
    assert device.session_extras()  # instanceid всё равно шлётся


def test_android_user_agent_matches_the_apk():
    """Набор полей снят с ru.oneme.app 26.29.1 (класс Lhti;)."""
    agent = Device.android(device_name="Pixel 8").to_user_agent()

    assert set(agent) == {
        "deviceType",
        "appVersion",
        "buildNumber",
        "osVersion",
        "arch",
        "locale",
        "deviceLocale",
        "deviceName",
        "screen",
        "pushDeviceType",
        "timezone",
    }
    assert agent["deviceType"] == "ANDROID"
    assert agent["deviceName"] == "Pixel 8"
    assert agent["appVersion"] == "26.29.1"
    assert agent["buildNumber"] == 6808
    assert agent["osVersion"] == "Android 13"   # String.format("Android %s", RELEASE)
    assert agent["arch"] == "arm64-v8a"         # Build.SUPPORTED_ABIS[0]
    assert agent["pushDeviceType"] == "GCM"
    # headerUserAgent мобильный клиент не шлёт вовсе
    assert "headerUserAgent" not in agent


def test_web_user_agent_keeps_browser_shape():
    agent = Device.web().to_user_agent()
    assert set(agent) == {
        "deviceType",
        "locale",
        "deviceLocale",
        "osVersion",
        "deviceName",
        "headerUserAgent",
        "appVersion",
        "screen",
        "timezone",
    }
    assert "arch" not in agent and "buildNumber" not in agent


def test_android_screen_format():
    from maxion.raw.device import android_screen

    assert android_screen(1080, 2400, 480) == "xxhdpi 480dpi 1080x2400"
    assert android_screen(1440, 3200, 640) == "xxxhdpi 640dpi 1440x3200"
    assert android_screen(720, 1280, 213) == "213dpi 213dpi 720x1280"  # редкая плотность


def test_android_screen_built_from_dimensions():
    agent = Device.android(width=1440, height=3200, dpi=640).to_user_agent()
    assert agent["screen"] == "xxxhdpi 640dpi 1440x3200"


def test_for_transport_picks_phone_profile():
    assert Device.for_transport("ANDROID").device_type is DeviceType.ANDROID
    assert Device.for_transport("WEB").device_type is DeviceType.WEB


async def _connect(**kwargs) -> MaxClient:
    transport = FakeTransport({Opcode.SESSION_INIT: {"isVpn": False}})
    client = MaxClient(
        transport=transport, ping_interval=0, auto_reconnect=False, **kwargs
    )
    await client.connect()
    return client


async def test_session_init_uses_android_profile():
    client = await _connect(device="android")
    try:
        payload = client.transport.sent[0].payload  # type: ignore[attr-defined]
        assert payload["userAgent"]["deviceType"] == "ANDROID"
        assert payload["userAgent"]["appVersion"] == "26.29.1"
        assert isinstance(payload["clientSessionId"], int)
        assert len(payload["mt_instanceid"]) == 32
    finally:
        await client.disconnect()


async def test_session_init_defaults_to_web():
    client = await _connect()
    try:
        payload = client.transport.sent[0].payload  # type: ignore[attr-defined]
        assert payload["userAgent"]["deviceType"] == "WEB"
        assert "clientSessionId" not in payload
        assert "mt_instanceid" not in payload
    finally:
        await client.disconnect()


async def test_user_agent_overrides_profile_fields():
    client = await _connect(
        device=Device.ios(), user_agent={"timezone": "Asia/Tashkent", "locale": "uz"}
    )
    try:
        agent = client.transport.sent[0].payload["userAgent"]  # type: ignore[attr-defined]
        assert agent["deviceType"] == "IOS"
        assert agent["timezone"] == "Asia/Tashkent"
        assert agent["locale"] == "uz"
    finally:
        await client.disconnect()


async def test_request_code_error_on_web_gets_actionable_hint():
    transport = FakeTransport(
        {
            Opcode.SESSION_INIT: {"isVpn": False},
            Opcode.AUTH_REQUEST: {"error": "unsupported", "message": "нельзя"},
        }
    )
    client = MaxClient(transport=transport, ping_interval=0, auto_reconnect=False)
    await client.connect()
    try:
        with pytest.raises(AuthError) as info:
            await client.request_code("+79991234567")
        assert 'device="android"' in str(info.value)
    finally:
        await client.disconnect()


async def test_request_code_on_phone_profile_passes_error_through():
    from maxion.raw.errors import RpcError

    transport = FakeTransport(
        {
            Opcode.SESSION_INIT: {"isVpn": False},
            Opcode.AUTH_REQUEST: {"error": "flood", "message": "часто"},
        }
    )
    client = MaxClient(
        transport=transport, device="android", ping_interval=0, auto_reconnect=False
    )
    await client.connect()
    try:
        with pytest.raises(RpcError):  # без подмешанной подсказки
            await client.request_code("+79991234567")
    finally:
        await client.disconnect()


async def test_successful_request_code_saves_phone():
    transport = FakeTransport(
        {
            Opcode.SESSION_INIT: {"isVpn": False},
            Opcode.AUTH_REQUEST: {"token": "tok", "codeLength": 6},
        }
    )
    client = MaxClient(
        transport=transport, device="android", ping_interval=0, auto_reconnect=False
    )
    await client.connect()
    try:
        payload = await client.request_code("8 999 123-45-67")
        assert payload["token"] == "tok"
        assert client.session.phone == "+79991234567"
        assert client.transport.sent[-1].payload == {  # type: ignore[attr-defined]
            "phone": "+79991234567",
            "type": "START_AUTH",
            "language": "ru",
        }
    finally:
        await client.disconnect()


def test_mobile_constructor_is_the_app():
    """MaxClient.mobile() -- бинарный протокол приложения плюс android-профиль."""
    from maxion.raw.transport import TcpTransport

    client = MaxClient.mobile()

    assert isinstance(client.transport, TcpTransport)
    assert client.transport.rpc_version == 10        # у приложения ver=10
    assert client.device.device_type is DeviceType.ANDROID
    assert client.device.supports_phone_auth
    assert client.transport.host == "api.oneme.ru"


def test_web_constructor_is_the_browser():
    from maxion.raw.transport import WebSocketTransport

    client = MaxClient.web()

    assert isinstance(client.transport, WebSocketTransport)
    assert client.transport.rpc_version == 11        # у web ver=11
    assert client.device.device_type is DeviceType.WEB


def test_mobile_allows_overrides():
    client = MaxClient.mobile(device=Device.ios(), auto_reconnect=False)
    assert client.device.device_type is DeviceType.IOS
    assert client.auto_reconnect is False
