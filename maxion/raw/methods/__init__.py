"""Миксины с методами API, собранные в один класс."""

from .assets import AssetMethods
from .auth import AuthMethods
from .calls import CallMethods, PollMethods
from .chats import ChatMethods
from .contacts import ContactMethods
from .media import MediaMethods
from .messages import MessageMethods
from .misc import MiscMethods
from .profile import ProfileMethods
from .reactions import ReactionMethods
from .stories import StoryMethods


class Methods(
    AuthMethods,
    ProfileMethods,
    ContactMethods,
    ChatMethods,
    MessageMethods,
    ReactionMethods,
    MediaMethods,
    AssetMethods,
    StoryMethods,
    CallMethods,
    PollMethods,
    MiscMethods,
):
    """Все методы MAX в одном интерфейсе."""


__all__ = [
    "Methods",
    "AuthMethods",
    "ProfileMethods",
    "ContactMethods",
    "ChatMethods",
    "MessageMethods",
    "ReactionMethods",
    "MediaMethods",
    "AssetMethods",
    "StoryMethods",
    "CallMethods",
    "PollMethods",
    "MiscMethods",
]
