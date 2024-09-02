from alliance_platform.core.settings import ap_core_settings
from django.apps import AppConfig
from django.db.models import Model


def default_resolve_perm_name(
    app_config: AppConfig,
    model: Model | type[Model] | None,
    action: str,
    is_global: bool,
) -> str:
    """Default implementation

    .. note::

        Don't call this directly; use :func:`~alliance_platform.core.auth.resolve_perm_name` which will call the function
        set in :data:`~alliance_platform.core.settings.AlliancePlatformCoreSettingsType.RESOLVE_PERM_NAME` (which defaults
        to ``default_resolve_perm_name``).

    Returns strings in the following format:

        With a model:     ``{app_config_label}.{model_name}_{action}``, e.g. ``"myapp.mymodel_list"``
        Without a model:  ``{app_config_label}.{action}``, e.g. ``"myapp.management"``

    We follow a different convention to django (model_action rather than action_model) so that permission
    names sort lexicographically.

    The default implementation makes no use of the ``is_global`` parameter.

    Args:
        app_config: The app config the permission is for. All permissions are scoped to an app.
        model: The model to use in the permission name. Can be ``None`` if permission is not specific to a model.
        action: The action to perform. For example, common ones include ``"create"``, ``"update"``, ``"detail"``, ``"list"``, ``"delete"`,
            but it can be anything.
        is_global: Whether the permission is global (``True``) or per-object (``False``). The default implementation does
            not use this parameter, but it is required for compatability with :data:`~alliance_platform.core.settings.AlliancePlatformCoreSettingsType.RESOLVE_PERM_NAME`.
    """
    if model:
        return f"{app_config.label}.{model._meta.model_name}_{action}"
    return f"{app_config.label}.{action}"


def resolve_perm_name(
    app_config: AppConfig,
    model: Model | type[Model] | None,
    action: str,
    is_global: bool,
) -> str:
    """Resolve a permission name for an app, model and action.

    This calls the function set in :data:`~alliance_platform.core.settings.AlliancePlatformCoreSettingsType.RESOLVE_PERM_NAME`,
    which defaults to :func:`~alliance_platform.core.auth.default_resolve_perm_name`.

    This method can be used when writing generic code that needs to generate a default permission name according to
    a convention.

    This method is compatable with the `django-csvpermissions CSV_PERMISSIONS_RESOLVE_PERM_NAME <https://github.com/AllianceSoftware/django-csvpermissions>`_
    setting.

    Usage:

    .. code-block:: pycon

        >>> resolve_perm_name(MyModel._meta.app_config, MyModel, "list", True)
        "myapp.mymodel_list"
        >>> resolve_perm_name(apps.get("myapp"), None, "management", True)
        "myapp.management"

    Args:
        app_config: The app config the permission is for. All permissions are scoped to an app.
        model: The model to use in the permission name. Can be ``None`` if permission is not specific to a model.
        action: The action to perform. For example, common ones include ``"create"``, ``"update"``, ``"detail"``, ``"list"``, ``"delete"`,
            but it can be anything.
        is_global: Whether the permission is global (``True``) or per-object (``False``).
    """
    return ap_core_settings.RESOLVE_PERM_NAME(app_config, model, action, is_global)
