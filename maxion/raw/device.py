"""Профили устройства для SESSION_INIT.

Сервер узнаёт клиента по объекту ``userAgent`` в SESSION_INIT (6). От него
зависит не только строчка в списке сессий, но и доступный набор методов:
в web-версии вырезана авторизация по номеру телефона, поэтому вход по SMS
делается с профилем телефона.

    MaxClient("my.session", device=Device.android())
    MaxClient("my.session", transport="tcp")   # профиль телефона подставится сам

Android-профиль снят с APK ``ru.oneme.app`` 26.29.1 (класс ``Lhti;`` и его
сборщик ``Liti;->a()``), поэтому набор полей у него другой, чем у браузера::

    deviceType     "ANDROID"                       (константа в конструкторе)
    appVersion     "26.29.1"                       (константа)
    buildNumber    6808                            (константа, int)
    osVersion      "Android 13"                    String.format("Android %s", RELEASE)
    arch           "arm64-v8a"                     Build.SUPPORTED_ABIS[0] либо "UNKNOWN"
    locale         "ru"
    deviceLocale   "ru"
    deviceName     "Xiaomi Redmi Note 12"          MANUFACTURER + " " + MODEL
    screen         "xxhdpi 480dpi 1080x2400"       бакет + dpi + ширина x высота
    pushDeviceType "GCM"                           enum: GCM | HUAWEI | RUSTORE
    timezone       "Europe/Moscow"                 TimeZone.getDefault().getID()

``headerUserAgent`` мобильный клиент не шлёт вовсе — это поле только web-версии.
Профили iOS и desktop собраны по аналогии и дампом не подтверждены.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from .enums import DeviceType, PushDeviceType

WEB_HEADER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
IOS_HEADER_UA = "MAX/26.29.1 (iPhone; iOS 17.5.1; Scale/3.00)"

#: Версия приложения, с которой снят android-профиль.
ANDROID_APP_VERSION = "26.29.1"
ANDROID_BUILD_NUMBER = 6808

#: Бакеты плотности из ``Liti;->a()``: densityDpi -> имя.
DENSITY_BUCKETS = {
    120: "ldpi",
    160: "mdpi",
    240: "hdpi",
    320: "xhdpi",
    480: "xxhdpi",
    640: "xxxhdpi",
}


def android_screen(width: int, height: int, dpi: int) -> str:
    """Строка ``screen`` в формате Android-клиента.

    >>> android_screen(1080, 2400, 480)
    'xxhdpi 480dpi 1080x2400'
    """
    bucket = DENSITY_BUCKETS.get(dpi, f"{dpi}dpi")
    return f"{bucket} {dpi}dpi {width}x{height}"


@dataclass
class Device:
    """Как клиент представляется серверу."""

    device_type: DeviceType | str = DeviceType.WEB
    device_name: str = "Chrome"
    os_version: str = "Linux"
    app_version: str = "26.2.2"
    screen: str = "1080x1920 1.0x"
    locale: str = "ru"
    device_locale: str = "ru"
    timezone: str = "Europe/Moscow"

    #: Только web-версия; мобильный клиент это поле не шлёт.
    header_user_agent: str | None = WEB_HEADER_UA

    #: Поля, которые есть только у приложения.
    arch: str | None = None
    build_number: int | None = None
    push_device_type: str | None = None

    #: Мобильные и десктопный досылают в SESSION_INIT ещё два поля.
    sends_instance_id: bool = False

    #: Что добавить или перекрыть в итоговом userAgent.
    extra: dict[str, Any] = field(default_factory=dict)

    # --- готовые профили ---------------------------------------------------

    @classmethod
    def web(cls, **overrides: Any) -> "Device":
        """Браузер — как web.max.ru. Вход по номеру телефона недоступен."""
        return cls(**overrides)

    @classmethod
    def android(
        cls,
        *,
        device_name: str = "Xiaomi Redmi Note 12",
        android_version: str = "13",
        app_version: str = ANDROID_APP_VERSION,
        build_number: int = ANDROID_BUILD_NUMBER,
        arch: str = "arm64-v8a",
        push_device_type: str = PushDeviceType.GCM.value,
        screen: str | None = None,
        width: int = 1080,
        height: int = 2400,
        dpi: int = 480,
        **overrides: Any,
    ) -> "Device":
        """Телефон на Android — набор полей снят с APK 26.29.1.

        ``device_name`` — как у клиента, ``MANUFACTURER + " " + MODEL``.
        ``screen`` собирается из ``width``/``height``/``dpi``, если не задан.
        """
        return cls(
            device_type=DeviceType.ANDROID,
            device_name=device_name,
            os_version=f"Android {android_version}",
            app_version=app_version,
            build_number=build_number,
            arch=arch,
            push_device_type=push_device_type,
            screen=screen or android_screen(width, height, dpi),
            header_user_agent=None,
            sends_instance_id=True,
            **overrides,
        )

    @classmethod
    def ios(
        cls,
        *,
        device_name: str = "iPhone 14",
        os_version: str = "iOS 17.5.1",
        app_version: str = ANDROID_APP_VERSION,
        screen: str = "1170x2532 3.0x",
        arch: str = "arm64",
        **overrides: Any,
    ) -> "Device":
        """Телефон на iOS. Дампом не подтверждён, собран по аналогии."""
        return cls(
            device_type=DeviceType.IOS,
            device_name=device_name,
            os_version=os_version,
            app_version=app_version,
            screen=screen,
            arch=arch,
            header_user_agent=IOS_HEADER_UA,
            sends_instance_id=True,
            **overrides,
        )

    @classmethod
    def desktop(
        cls,
        *,
        device_name: str = "Windows",
        os_version: str = "Windows 10.0.26200",
        app_version: str = ANDROID_APP_VERSION,
        **overrides: Any,
    ) -> "Device":
        """Десктопное приложение. Дампом не подтверждён."""
        return cls(
            device_type=DeviceType.DESKTOP,
            device_name=device_name,
            os_version=os_version,
            app_version=app_version,
            header_user_agent=None,
            sends_instance_id=True,
            **overrides,
        )

    @classmethod
    def for_transport(cls, device_type: str) -> "Device":
        """Профиль по умолчанию для транспорта."""
        return {
            DeviceType.ANDROID.value: cls.android,
            DeviceType.IOS.value: cls.ios,
            DeviceType.DESKTOP.value: cls.desktop,
        }.get(str(device_type), cls.web)()

    # --- сериализация ------------------------------------------------------

    @property
    def is_mobile(self) -> bool:
        return str(self.device_type) in (
            DeviceType.ANDROID.value,
            DeviceType.IOS.value,
        )

    @property
    def supports_phone_auth(self) -> bool:
        """В web-клиенте вход по номеру телефона недоступен."""
        return str(self.device_type) != DeviceType.WEB.value

    def to_user_agent(self) -> dict[str, Any]:
        """Объект ``userAgent`` для SESSION_INIT.

        Поля, которых у профиля нет, не отправляются: браузер не шлёт ``arch``
        и ``buildNumber``, приложение — ``headerUserAgent``.
        """
        agent: dict[str, Any] = {
            "deviceType": str(self.device_type),
            "locale": self.locale,
            "deviceLocale": self.device_locale,
            "osVersion": self.os_version,
            "deviceName": self.device_name,
            "appVersion": self.app_version,
            "screen": self.screen,
            "timezone": self.timezone,
        }
        if self.header_user_agent:
            agent["headerUserAgent"] = self.header_user_agent
        if self.arch:
            agent["arch"] = self.arch
        if self.build_number is not None:
            agent["buildNumber"] = self.build_number
        if self.push_device_type:
            agent["pushDeviceType"] = self.push_device_type
        agent.update(self.extra)
        return agent

    def session_extras(self) -> dict[str, Any]:
        """Доп. аргументы :meth:`~maxion.raw.methods.auth.AuthMethods.session_init`.

        Мобильные и десктопные клиенты досылают в SESSION_INIT свой
        ``clientSessionId`` и ``mt_instanceid``; браузер — нет.
        """
        if not self.sends_instance_id:
            return {}
        return {
            "client_session_id": random.getrandbits(48),
            "instance_id": uuid.uuid4().hex,
        }

    def __repr__(self) -> str:
        return f"<Device {self.device_type} {self.device_name!r} {self.app_version}>"
