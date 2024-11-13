from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import Literal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.utils.module_loading import import_string


def maybe_import_string(val: Any | None):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """
    if val is None:
        return None
    elif isinstance(val, str):
        return import_string(val)
    return val


SettingKey = Literal["CORE", "FRONTEND", "CODEGEN", "STORAGE", "AUDIT"]


class AlliancePlatformSettingsBase:
    _has_loaded = False
    # This is a dict of settings, type will be one of the TypedDicts defined in the settings module. Typing as Any
    # to avoid errors like `Incompatible types in assignment` - can't strictly type this as this common module is copied
    # into each package and doesn't know anything about them
    _user_settings: Any = {}

    _key: SettingKey
    _defaults: dict[str, Any]
    _import_strings: list[str]

    def __init__(
        self, key: SettingKey, defaults: dict | None = None, import_strings: list[str] | None = None
    ):
        self._key = key
        self._defaults = defaults or {}
        self._import_strings = import_strings or []
        self._path_strings = [k for k, v in self.__class__.__annotations__.items() if v is Path]

        setting_changed.connect(self._reload_api_settings)

    def _reload_api_settings(self, *args, **kwargs):
        setting = kwargs["setting"]
        if setting == "ALLIANCE_PLATFORM":
            self.reload()

    def _load_user_settings(self):
        self._has_loaded = True
        try:
            platform_settings = settings.ALLIANCE_PLATFORM
        except AttributeError:
            raise ImproperlyConfigured(
                "Missing ALLIANCE_PLATFORM settings dict - check that you have not imported alliance_platform.frontend.settings before defining your ALLIANCE_PLATFORM settings dict"
            )
        try:
            self._user_settings = platform_settings[self._key]
        except KeyError:
            # Don't throw an error if not set so things work with packages that only have optional settings
            self._user_settings = {}

    @lru_cache()
    def __getattr__(self, key):
        if not self._has_loaded:
            self._load_user_settings()
        try:
            value = self._user_settings.get(key) if key in self._user_settings else self._defaults[key]
        except KeyError:
            raise ImproperlyConfigured(
                f"Missing required setting '{key}' in ALLIANCE_PLATFORM[\"{self._key}\"] settings"
            )
        if isinstance(value, LazySetting):
            value = value()
        if key in self._import_strings:
            try:
                value = maybe_import_string(value)
            except ImportError as e:
                msg = f"Could not import '{value}' for ALLIANCE_PLATFORM[\"{self._key}\"] setting '{key}'. {e.__class__.__name__}: {e}."
                raise ImportError(msg)
        if key in self._path_strings and isinstance(value, str):
            value = Path(value)
        return value

    def reload(self):
        self.__getattr__.cache_clear()
        self._load_user_settings()

    def check_settings(self):
        """Can be implemented to check settings are valid when app is ready"""
        pass


class LazySetting:
    def __init__(self, getter):
        self.getter = getter

    def __call__(self):
        return self.getter()
