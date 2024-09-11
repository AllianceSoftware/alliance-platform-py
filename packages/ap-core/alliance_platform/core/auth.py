from typing import overload

from alliance_platform.core.settings import ap_core_settings
from django.apps import AppConfig
from django.db.models import Model


def default_resolve_perm_name(
    app_config: AppConfig,
    model: Model | type[Model] | None,
    action: str,
    is_global: bool,
) -> str:
    """Default implementation of :func:`~alliance_platform.core.auth.resolve_perm_name`.

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
        app_config: The app config the permission is for. All permissions are scoped to an app. If ``model``, you can pass
            ``model._meta.app_config`` here..
        model: The model to use in the permission name. Can be ``None`` if permission is not specific to a model.
        action: The action to perform. For example, common ones include ``"create"``, ``"update"``, ``"detail"``, ``"list"``, ``"delete"``,
            but it can be anything.
        is_global: Whether the permission is global (``True``) or per-object (``False``). The default implementation does
            not use this parameter, but it is required for compatability with :data:`~alliance_platform.core.settings.AlliancePlatformCoreSettingsType.RESOLVE_PERM_NAME`.
    """
    if model:
        return f"{app_config.label}.{model._meta.model_name}_{action}"
    return f"{app_config.label}.{action}"


@overload
def resolve_perm_name(entity: Model | type[Model], action: str, is_global: bool) -> str:
    """Resolve a permission name for a model and action."""
    ...


@overload
def resolve_perm_name(entity: AppConfig, action: str, is_global: bool) -> str:
    """Resolve a permission name for an app and action"""
    ...


def resolve_perm_name(
    entity: Model | type[Model] | AppConfig,
    action: str,
    is_global: bool,
) -> str:
    """Resolve a permission name for an app or model, and an action.

    This calls the function set in :data:`~alliance_platform.core.settings.AlliancePlatformCoreSettingsType.RESOLVE_PERM_NAME`,
    which defaults to :func:`~alliance_platform.core.auth.default_resolve_perm_name`.

    This method can be used when writing generic code that needs to generate a default permission name according to
    a convention. For example, on generic CRUD views.

    Usage for model permissions:

    .. code-block:: pycon

        >>> resolve_perm_name(MyModel, "list", True)
        "myapp.mymodel_list"
        >>> record = MyModel.objects.get(pk=5)
        >>> resolve_perm_name(record, "update", False)
        "myapp.mymodel_update"

    For permissions that are not specific to a model, pass an :class:`~django.apps.AppConfig` instead of a model:

    .. code-block:: pycon

        >>> from django.apps import apps
        >>> resolve_perm_name(apps.get_app_config("MyApp"), "dashboard", True)
        "myapp.dashboard"

    .. note::

        The default implementation makes no use of the ``is_global`` parameter, but custom implementations may so it
        is required.

    Args:
        entity: This will either by an :class:`~django.apps.AppConfig`, or a :class:`~django.db.models.Model` class or instance.
            All permissions are scoped to an app; if a model is passed the config will be extracted from the model.
        action: The action to perform. For example, common ones for a model include ``"create"``, ``"update"``, ``"detail"``,
            ``"list"``, ``"delete"``, but it can be anything.
        is_global: Whether the permission is global (``True``) or per-object (``False``).
    """
    if isinstance(entity, Model) or (isinstance(entity, type) and issubclass(entity, Model)):
        app_config = entity._meta.app_config
        model = entity
    elif isinstance(entity, AppConfig):
        app_config = entity
        model = None
    else:
        raise ValueError("First argument must be a model or an app config.")

    return ap_core_settings.RESOLVE_PERM_NAME(app_config, model, action, is_global)
