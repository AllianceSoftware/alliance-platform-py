from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from alliance_platform.base_settings import LazySetting
from django.conf import settings


class AlliancePlatformUISettingsType(TypedDict, total=False):
    """The type of the settings for the UI of the Alliance Platform.

    Set these under ``ALLIANCE_PLATFORM["UI"]`` in your Django settings. All are optional.
    """

    #: If true, a ``contract`` diagnostic from a static ``{% ui %}`` component raises
    #: :class:`~alliance_platform.ui.html_components.diagnostics.StaticComponentContractError`
    #: instead of logging. ``data`` diagnostics never raise. Defaults to the value of ``DEBUG``.
    STATIC_COMPONENT_STRICT: bool


class AlliancePlatformUISettings(AlliancePlatformSettingsBase):
    #: If true, ``contract`` diagnostics from static ``{% ui %}`` components raise instead of logging
    STATIC_COMPONENT_STRICT: bool

    def _reload_api_settings(self, *args, **kwargs):
        super()._reload_api_settings(*args, **kwargs)
        if kwargs["setting"] == "DEBUG":
            # STATIC_COMPONENT_STRICT defaults to DEBUG, so drop the cached value when DEBUG changes
            self.__getattr__.cache_clear()


DEFAULTS = {
    "STATIC_COMPONENT_STRICT": LazySetting(lambda: settings.DEBUG),
}

ap_ui_settings = AlliancePlatformUISettings("UI", defaults=DEFAULTS)
