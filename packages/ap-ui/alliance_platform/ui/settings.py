from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase


class AlliancePlatformUISettingsType(TypedDict, total=False):
    """The type of the settings for the UI of the Alliance Platform.

    Currently just a placeholder as the UI package doesn't yet need
    any settings of its own.
    """


class AlliancePlatformUISettings(AlliancePlatformSettingsBase):
    pass


ap_ui_settings = AlliancePlatformUISettings("UI")
