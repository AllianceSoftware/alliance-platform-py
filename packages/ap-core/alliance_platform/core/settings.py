from pathlib import Path
from typing import Callable
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from alliance_platform.base_settings import LazySetting
from django.apps import AppConfig
from django.db.models import Model

RESOLVE_PERM_NAME_TYPE = Callable[[AppConfig, Model | type[Model] | None, str, bool], str]


class AlliancePlatformCoreSettingsType(TypedDict, total=False):
    """Settings for the core package of the Alliance Platform

    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:

    .. code-block:: python

        ALLIANCE_PLATFORM = {
            "CORE": {
                "PROJECT_DIR": PROJECT_DIR,
            }
        }
    """

    #: The root directory of the project
    PROJECT_DIR: Path | str
    #: A directory used for caching. This is used by various packages. If not set, defaults to ``PROJECT_DIR / '.alliance-platform'``
    CACHE_DIR: Path | str | None
    RESOLVE_PERM_NAME: str | RESOLVE_PERM_NAME_TYPE
    """
    A function used to resolve a permission name for a model and action. You can set this to function, or an import
    path to a function. The function should have the signature:
    
    .. code-block:: python
    
        def custom_resolve_perm_name(
            # When `model` is passed, `app_config` will be set to `model._meta.app_config`
            app_config: AppConfig,
            # The model class or instance
            model: Model | type[Model] | None,
            # The name of the action. This can be any string, but common ones for CRUD actions
            # are "create", "update", "detail", "list", "delete".
            action: str,
            # Whether the permission is global (``True``) or per-object (``False``). The
            # default implementation does not make use of this parameter, but a custom
            # implementation may.
            is_global: bool
        ) -> str: ...
        
    This is used by the :func:`~alliance_platform.core.auth.resolve_perm_name` function, and is used throughout
    alliance_platform when a generic default permission is needed for a model or app. You can see
    :func:`~alliance_platform.core.auth.default_resolve_perm_name` for an example, and the default used
    when none is provided.
    """


class AlliancePlatformCoreSettings(AlliancePlatformSettingsBase):
    PROJECT_DIR: Path
    CACHE_DIR: Path
    RESOLVE_PERM_NAME: RESOLVE_PERM_NAME_TYPE


DEFAULTS = dict(
    CACHE_DIR=LazySetting(lambda: ap_core_settings.PROJECT_DIR / ".alliance-platform"),  # type: ignore[has-type]
    RESOLVE_PERM_NAME="alliance_platform.core.auth.default_resolve_perm_name",
)

ap_core_settings = AlliancePlatformCoreSettings(
    "CORE",
    defaults=DEFAULTS,
    import_strings=["RESOLVE_PERM_NAME"],
)
