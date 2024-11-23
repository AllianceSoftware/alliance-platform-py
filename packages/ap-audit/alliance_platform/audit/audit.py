from collections import defaultdict
from collections.abc import Callable
from collections.abc import Iterable
import copy
from typing import TYPE_CHECKING
from typing import cast

from alliance_platform.audit.events import AuditSnapshot
from alliance_platform.audit.events import create_event
from alliance_platform.audit.registry import AuditRegistry
from alliance_platform.audit.registry import _registration_by_model
from alliance_platform.audit.registry import default_audit_registry
from alliance_platform.audit.utils import get_model_module
from alliance_platform.core.auth import resolve_perm_name
from allianceutils.auth.permission import NoDefaultPermissionsMeta
from django.contrib.postgres.fields import ArrayField
from django.db import models
import pghistory
from pghistory import constants
from pghistory.core import _registered_trackers

from .settings import ap_audit_settings

if TYPE_CHECKING:
    # we can't run this
    class AuditableModelProtocol(models.Model):
        """Protocol for auditable models.

        Any django model is auditable. You can use this type when expecting an auditable model.
        """

        # this should be a Protocol but both Model and Protocol have conflicting metaclasses

        __name__: str  # django type stubs don't include this but it's there
        __qualname__: str

        AuditEvent: type[models.Model] | None

else:

    class AuditableModelProtocol:
        pass


def create_audit_model_base(
    model: type[AuditableModelProtocol],
    *,
    meta_base: type = object,
    manual_events: list[str] | None = None,
    events: list[pghistory.Tracker] | None = None,
    registry: AuditRegistry = default_audit_registry,
    list_perm: str | None = None,
    fields: list[str] | None = None,
    exclude: list[str] | None = None,
    related_name: str | constants.Unset = constants.UNSET,
    **kwargs,
) -> type[models.Model]:
    """
    Given :code:`model`, returns a base to be used for creating a table to attach audit log to:

    .. code-block:: python

        class UserAuditEvent(
            create_audit_model_base(User, exclude=["password", "last_login"], manual_events=["LOGIN", "LOGOUT"])
        ):
            class Meta:
                db_table = "xenopus_frog_user_auditevent"

    Should you wish to add events that are manually-triggered eg a pdf file had been downloaded, just specify
    those events in ``manual_events``; to then trigger a manual event use :meth:`~alliance_platform.audit.create_audit_event`.

    :code:`events` refers to the :external:class:`~pghistory.RowEvent` to be used which defaults to
    :class:`~alliance_platform.audit.events.AuditSnapshot`. This audits :code:`CREATE`, :code:`UPDATE` and :code:`DELETE` events and
    has handling for many to many fields. You most likely do not need to change this option.

    If you need to monitor other database events, such as BeforeInsert, you could do so by passing in
    :code:`events`; this will supersede AuditSnapshot which if you intend to keep can be done by adding
    :code:`AuditSnapshot(label="your label")` to the list. See :class:`~alliance_platform.audit.events.AuditSnapshot`
    to see what you need to be aware of before doing this.

    One noteworthy kwarg is ``fields``, where you can ask the audit module to only watch changes made to
    your selected list of fields. By default, all fields are tracked, and should be kept this way unless
    you have a good reason to change this behavior. If you wish to record all fields but only display some
    of them on frontend (eg, sensitive fields), then define :code:`audit_fields_to_display` on your model.

    FileField and ImageField are recorded as string (URL), AutoField is recorded as IntegerField and
    any ManyToManyField is recorded only on the sourcing side as an ArrayField with same field name
    (eg. ``bug=ManyToManyField(Bug)`` on ``Coder`` will result in an array of bug's ids being recorded
    in ``coder.events.bug``, but this field will not be created on the Bug model even if its also audited)

    See :external:func:`pghistory.core.create_event_model` for the supported ``kwargs`` and more details

    Usage::

        class PDFAuditEvent(create_audit_model_base(PDFFile, manual_events=["accessed"])):
            audit_fields_to_display=['id', 'uploader', 'file']
            class Meta:
                db_table = "pdf_file_audit_log"

        # You must pass the record the event is logged against. Acting user is also tracked (by default)
        # by AuditMiddleware and stored in context.
        create_audit_event(pdf, "accessed")

    Args:
        model: The model to create audit event model for
        meta_base: The base class for Meta, eg. NoDefaultPermissionsMeta
        manual_events: List of manual events supported for this model
        events: Database events to monitor. See above comments for more details.
        registry: The audit registry to add to. You most likely don't need this; the default suffices for most cases
        list_perm: The permission to use when showing audit events in list view. This should be a global
            permission (ie. doesn't accept a specific object). If not specified uses :external:func:`~alliance_platform.core.auth.resolve_perm_name`
            with an action of ap_audit_settings.LIST_PERM_ACTION (which defaults to ``audit``) for the model ``model``
            (ie. the source model).
        fields: The fields to track. If None, all fields on :code:`model` are tracked.
        exclude: Exclude these fields from tracking. Only one of :code:`fields` and ``exclude`` should be specified.
        related_name (str): The primary way to identify the relation of the created model and the tracked model. If
            ``fields`` or ``exclude`` are not provided this defaults to ``auditevents`` otherwise a name is generated based on
            the provided fields (see :external:func:`pghistory.core.create_event_model`).
    """
    if fields and exclude:
        raise ValueError("Only one of `fields` and `exclude` should be specified")

    if not fields and (related_name == constants.UNSET):
        # This restores the original default behaviour of pghistory. If you pass fields
        # it generates a name based on that. We always pass fields now but we
        # can restore original behaviour by setting it based on what was passed in
        # Note that pghistory sets to base_model._meta.object_name.lower() - you
        # can't change base_model here and so we hardcode to 'auditevents'

        # new default behaviour is to avoid creating related names altogether, but we
        # do want related names in our case
        related_name = "auditevents"
    exclude = exclude or []
    fields = fields or [f.name for f in model._meta.fields if f.name not in exclude]

    inherited_fields_by_model = defaultdict(list)
    inherited_fields = []
    for fname in fields:
        field = model._meta.get_field(fname)
        if field.model != model:
            inherited_fields_by_model[field.model].append(field.name)
            inherited_fields.append(field.name)
    parent_model_registrations = []
    for parent_model, field_names in inherited_fields_by_model.items():
        registration = registry.get_registration_by_model(parent_model)
        parent_model_registrations.append(registration)
        if not registration:
            raise ValueError(
                f"Fields {', '.join(sorted(field_names))} exist only on the parent model {parent_model.__name__} "
                f"which is not being audited. Either exclude these fields from '{model.__name__}' or audit '{parent_model.__name__}' "
                f"and include these fields."
            )
        else:
            missing_fields = sorted(
                set(field_names).difference(set(field.name for field in registration.get_audited_fields()))
            )
            if missing_fields:
                raise ValueError(
                    f"Fields {', '.join(missing_fields)} exist only on the parent model {parent_model.__name__} "
                    f"but the audit model '{registration.event_model.__name__}' does not include these fields. You "
                    f"must either include these fields in '{registration.event_model.__name__}' or exclude them "
                    f"from this model"
                )

    fields = [field for field in fields if field not in inherited_fields]

    if not fields:
        raise ValueError(
            f"There are no auditable fields on model {model.__name__}. Check whether you excluded all"
            f"fields or if its fields all came from a parent model."
        )

    if not events:
        events = [AuditSnapshot(label=f"{model._meta.app_label}.{model._meta.model_name}")]

    if manual_events:
        for e in manual_events:
            events.append(pghistory.Tracker(e))

    base_event_cls = pghistory.create_event_model(
        model,
        *events,
        fields=fields,
        obj_field=pghistory.ObjForeignKey(related_name=related_name),
        **kwargs,
    )

    attrs = {
        "pgh_previous": models.ForeignKey("self", on_delete=models.SET_NULL, null=True),
        "Meta": type("Meta", (meta_base,), {"abstract": True}),
        "__module__": get_model_module(model),
    }

    if m2ms := getattr(model._meta, "many_to_many", None):
        for m2m in m2ms:
            if m2m.name in exclude:
                continue
            pkfield = copy.deepcopy(model._meta.pk)
            if isinstance(pkfield, (models.AutoField, models.ForeignKey)):
                pkfield = models.IntegerField()

            if pkfield:
                attrs[m2m.name] = ArrayField(pkfield, blank=True, null=True)

    BaseAuditModel = type(model.__name__ + "BaseAudit", (base_event_cls,), attrs)
    if list_perm is None:
        list_perm = resolve_audit_list_perm(model)
    registry.register(model, BaseAuditModel, manual_events, list_perm, parent_model_registrations)

    return BaseAuditModel


def resolve_audit_list_perm(model: type[models.Model]) -> str:
    return resolve_perm_name(
        entity=model,
        action=cast(str, ap_audit_settings.LIST_PERM_ACTION),
        is_global=True,
    )


def with_audit_model(
    meta_base: type = NoDefaultPermissionsMeta,
    audit_fields_to_display: Iterable[str] | None = None,
    **kwargs,
) -> Callable[[type[models.Model]], models.Model]:
    """
    Model class decorator to create an associated audit model

    Wraps :func:`~alliance_platform.audit.create_audit_model_base` in decorator form and adds some sensible defaults
    """

    def decorate(model: type[AuditableModelProtocol]) -> type[models.Model]:
        base_class = create_audit_model_base(model, meta_base=meta_base, **kwargs)
        meta_attrs = {
            "db_table": model._meta.db_table + "_auditevent",
        }
        attrs = {
            "Meta": type("Meta", (meta_base,), meta_attrs),
            "__module__": get_model_module(model),
            "__qualname__": f"{model.__qualname__}.AuditEvent",
        }
        if audit_fields_to_display is not None:
            attrs["audit_fields_to_display"] = audit_fields_to_display
        audit_model = type(model.__name__ + "AuditEvent", (base_class,), attrs)

        model.AuditEvent = audit_model
        return model

    return cast(Callable[[type[models.Model]], models.Model], decorate)


def create_audit_event(object: models.Model, label: str) -> models.Model:
    """
    Manually logs an event against a preset manual-event for object's class, eg:
    :code:`create_audit_event(pdf, "accessed")`.

    The event must be registered on the specified model (eg. should be passed in :code:`manual_events` to
    :func:`~alliance_platform.audit.create_audit_model_base`).

    All manual log entries are tied to objects (ie, you can't have object-less events such as
    :code:`create_audit_event("system shutdown")` ). By default, :meth:`~alliance_platform.audit.middleware.AuditMiddleware` tracks and records
    the current user and URL in the :external:code:`pgh_context` for the created log event, and additional info can be
    added by wrapping :code:`create_audit_event` in :code:`with pghistory.context(**kwargs)`. See :external:class:`pghistory.context`
    for more details about how context works.

    Returns created event model.
    """
    model = object.__class__
    registration = _registration_by_model[model]
    # Allow adding a custom event against descendant model - will add it to correct parent
    parent_model_registrations = registration.parent_model_registrations.copy()
    while parent_model_registrations and label not in registration.manual_events:
        registration = parent_model_registrations.pop()
    if label not in registration.manual_events:
        raise ValueError(
            f"{label} is not a valid manual event for {model}. Make sure it had been included in manual_events passed to create_audit_model_base."
        )

    # We need to modify the _registered_trackers list in pghistory in order to bypass its
    # check of the same functionality (and we cant do this in setup because we dont know
    # about the final model as we're not using the decorator approach)
    _registered_trackers[(model, label)] = registration.event_model

    return create_event(object, registration, label=label)
