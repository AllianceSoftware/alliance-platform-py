from typing import Any
from typing import Type
from typing import cast

from allianceutils.template import resolve
from allianceutils.util import camelize
from django import template
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.template import Context
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE
from django.template.exceptions import TemplateSyntaxError
from django.urls import NoReverseMatch
from django.urls import reverse
from django.urls import reverse_lazy

from alliance_platform.audit.registry import default_audit_registry
from alliance_platform.audit.settings import ap_audit_settings

try:
    from alliance_platform.frontend.bundler import get_bundler
    from alliance_platform.frontend.bundler.base import ResolveContext
    from alliance_platform.frontend.templatetags.react import ComponentNode
    from alliance_platform.frontend.templatetags.react import ComponentProps
    from alliance_platform.frontend.templatetags.react import ComponentSourceBase
    from alliance_platform.frontend.templatetags.react import ImportComponentSource
    from alliance_platform.frontend.templatetags.react import parse_component_tag
except ImportError as e:
    raise ImproperlyConfigured(
        "Optional dependency 'alliance_platform.frontend' is not installed. This is required to render audit templatetags."
    ) from e

register = template.Library()


class AuditListNode(ComponentNode):
    def __init__(self, origin: Origin, source: ComponentSourceBase, props: dict[str, Any], **kwargs):
        self.registry = props.pop("registry", default_audit_registry)
        self.model_name = props.pop("model", None)
        self.object: Type[models.Model] = props.pop("object", None)
        self.pk: int | None = props.pop("pk", None)
        self.limit_to_user = props.pop("limit_to_user", None)
        super().__init__(origin, source, props, **kwargs)

    def resolved_kwargs(self, context: Context):
        pk = resolve(self.pk, context)
        model = resolve(self.model_name, context)
        object = resolve(self.object, context)
        registry = resolve(self.registry, context)
        registrations = registry.get_registrations_for_user(context["request"].user)
        limit_to_user = resolve(self.limit_to_user, context)
        if pk and object:
            raise ValueError(
                f"You passed both `pk` and `object` to render_audit_list for {model}. Use one or the other."
            )

        if model and object:
            raise ValueError(
                f"You passed both `model` and `object` to render_audit_list for {model}. Use one or the other."
            )

        if pk and model == "all":
            raise ValueError(
                "You passed both `model=all` to render_audit_list but also supplied a `pk`. This is not allowed."
            )
        registration = None
        if model != "all":
            if model:
                from django.apps import apps

                app_label, model_name = model.split(".")
                model = apps.get_model(app_label=app_label, model_name=model_name)
            else:
                model = object.__class__
                pk = object.pk
            registration = registry.get_registration_by_model(model)
            if not registration:
                raise ValueError(f"No audit registration found for {model}")

        return model, pk, registrations, registry, registration, limit_to_user

    def render(self, context):
        model, pk, registrations, registry, registration, limit_to_user = self.resolved_kwargs(context)
        if model != "all":
            # Check that the requested registration is available to the current user
            if registration not in registrations:
                return ""

        return super().render(context)

    def resolve_props(self, context: Context) -> ComponentProps:
        props = super().resolve_props(context)
        model, pk, registrations, registry, registration, limit_to_user = self.resolved_kwargs(context)

        api_url = reverse_lazy(registry.attached_view)

        try:
            # reverse_lazy will only trigger the error when the URL is actually accessed - not what we want
            # for this try/except
            url = reverse(default_audit_registry.user_choices_view)
        except NoReverseMatch:
            raise ValueError("AsyncChoices are required but AuditUserChoicesView has not been registered.")

        props.update(
            camelize(
                dict(
                    limit_to_user=limit_to_user,
                    api_url=api_url,
                    user_async_choices=dict(
                        api_url=url,
                    ),
                )
            )
        )

        if model == "all":
            # Note: it's possible that a user would have permission to view audit logs in general,
            # but not have the required permission to list any given specific model - in which
            # case 'registrations' here will be empty. We could also choose to not render the AuditLog
            # component at all in this case.
            _models = [reg.event_model._base_manager.only("pgh_label") for reg in registrations]
            labels = (
                sorted(
                    set(
                        _models[0]
                        .union(*_models[1:])
                        .order_by("pgh_label")
                        .values_list("pgh_label", flat=True)
                    )
                )
                if registrations
                else ""
            )
            labels_by_model = {reg.model_label: reg.get_audited_field_labels() for reg in registrations}
            props.update(
                camelize(
                    dict(
                        model="all",
                        field_labels=labels_by_model,
                        labels=labels,
                    )
                )
            )
            return props

        # we'll run one more query to see what are labels filterable for this model/event
        events = registration.event_model._base_manager.all().only("pgh_label")
        if pk:
            events = events.filter(pgh_obj_id=pk)
        if registration.parent_model_registrations:
            other_events = []
            for reg in registration.parent_model_registrations:
                parent_events = reg.event_model._base_manager.all().only("pgh_label")
                if pk:
                    parent_events = parent_events.filter(pgh_obj_id=pk)
                other_events.append(parent_events)
            events = events.union(*other_events)
        labels = sorted(set(events.order_by("pgh_label").values_list("pgh_label", flat=True)))
        field_labels = {
            reg.model_label: reg.get_audited_field_labels()
            for reg in [registration, *registration.parent_model_registrations]
        }
        props.update(
            camelize(
                dict(
                    model=registration.model_hash,
                    field_labels=field_labels,
                    pk=pk,
                    labels=labels,
                )
            )
        )
        return props


@register.tag()
def render_audit_list(parser: template.base.Parser, token: template.base.Token):
    """
    Renders an audit log list in one of three modes:

    - supply :code:`model` but not :code:`pk`, and model is not :code:`all`:

      renders an antd table that lists all events related to all instances of ``model``

    - supply :code:`model="all"`:

      renders an antd table that lists all changes accessible by user across all audited models

    - supply :code:`model` with :code:`pk`, or :code:`object`:

      renders an antd table that lists only events recorded for that object

    Requires ``alliance_platform.frontend`` to be installed, and the ap_audit_settings.AUDIT_LOG_COMPONENT_PATH to
    point to a react component in your frontend source folder that renders the audit log component.

    Args:
        context: django context for the purpose of accessing user. provided by default.
        model: the string name of a model either being "all" or in the format of ``app.model`` eg ``admin.user``
        object: an instance of object being audited, if you have one,
        pk: or the object's pk (use in conjuration with ``model``) if you don't have the instance
        registry: registry to use. you most likely don't need to touch this one.
        limit_to_user: restrict events to only those made by the user, where supplied user is either the actor or hijacker
        **kwargs: Any other props to pass through to :code:`AuditLog.tsx`

    """
    bundler = get_bundler()
    origin = parser.origin or Origin(UNKNOWN_SOURCE)
    resolver_context = ResolveContext(bundler.root_dir, origin.name)
    component_path = ap_audit_settings.AUDIT_LOG_COMPONENT_PATH
    try:
        source_path = get_bundler().resolve_path(
            cast(str, component_path),
            resolver_context,
            resolve_extensions=[".ts", ".tsx", ".js"],
        )
    except TemplateSyntaxError:
        raise ImproperlyConfigured(
            f"Unable to locate audit log component at {component_path} - check that AUDIT_LOG_COMPONENT_PATH points to a valid React component export"
        )

    asset_source = ImportComponentSource(source_path, "AuditLog", True)
    return parse_component_tag(
        parser, token, node_class=AuditListNode, asset_source=asset_source, no_end_tag=True
    )
