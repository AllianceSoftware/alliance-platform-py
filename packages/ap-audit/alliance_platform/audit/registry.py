from __future__ import annotations

from dataclasses import Field
from dataclasses import dataclass
import hashlib
from typing import Protocol
from typing import cast

from alliance_platform.audit.settings import ap_audit_settings
from alliance_platform.audit.utils import is_m2m
from django.db import models
from django.db.models.fields.related_descriptors import ForwardOneToOneDescriptor

_registration_by_model: dict[type[models.Model], AuditModelRegistration] = {}


def get_audited_fields(model, ignore_m2m: bool = False, ignore_pk: bool = False) -> list[models.Field]:
    """
    helper func; return fields being audited for `model`
    accepts `event_model` as a param for usage
    """
    fields = []
    event_model = _registration_by_model[model].event_model
    for f in event_model._meta.fields:
        if not isinstance(f, models.AutoField) and hasattr(model, f.name):
            if (not ignore_m2m or not is_m2m(model, f.name)) and (
                not ignore_pk or f.name != model._meta.pk.name
            ):
                fields.append(f)
    return fields


class AuditedModelProtocol(Protocol):
    pgh_tracked_model: type[models.Model]


@dataclass
class AuditModelRegistration:
    model: type[models.Model]
    manual_events: list[str]
    base_audit_model: type[models.Model]
    registry: AuditRegistry
    list_perm: str
    # These are in order from nearest to furthest ancestor
    parent_model_registrations: list[AuditModelRegistration]
    # This is displayed to users on frontend
    model_label: str | None = None

    def __post_init__(self):
        if self.model_label is None:
            self.model_label = self.model.__name__

    @property
    def event_model(self) -> type[models.Model]:
        """Get the actual event model for this registered model"""
        # TODO - DO THIS W/ META CLASS?
        return self.base_audit_model.__subclasses__()[0]

    @property
    def model_hash(self):
        return self.registry.hash_model(self.model)

    def get_audited_fields(self, ignore_m2m: bool = False, ignore_pk: bool = False) -> list[models.Field]:
        """
        helper func; return fields being audited for `model`
        accepts `event_model` as a param for usage
        """
        return get_audited_fields(self.model, ignore_m2m=ignore_m2m, ignore_pk=ignore_pk)

    def get_audited_field_labels(self):
        """
        returns fields->verbose name mapping.
        """
        audit_fields_to_display = getattr(self.event_model, "audit_fields_to_display", "__all__")

        # we by default try to suppress ptr fields unless they're specified in audit_fields_to_display
        # a field will be suppressed if its the pk field for the model but is also an one-to-one
        res = [
            (f.name, f.verbose_name)
            for f in self.get_audited_fields()
            if (
                audit_fields_to_display == "__all__"
                and not (
                    cast(Field, cast(AuditedModelProtocol, f.model).pgh_tracked_model._meta.pk).name
                    == f.name  # pgh_tracked_model would be type[model] not model and thus the .pk is never optional but mypy dont understand this
                    and isinstance(
                        getattr(cast(AuditedModelProtocol, f.model).pgh_tracked_model, f.name),
                        ForwardOneToOneDescriptor,
                    )
                )
            )
            or f.name in audit_fields_to_display
        ]

        return dict(res)


class AuditRegistry:
    registrations: dict[type[models.Model], AuditModelRegistration]
    registrations_by_hash: dict[str, AuditModelRegistration]

    def __init__(self):
        self.registrations = {}
        self.registrations_by_hash = {}
        self.attached_view = None
        self.user_choices_view = None

    def get_registration_by_model(self, model):
        return self.registrations.get(model, None)

    def get_registration_by_hash(self, hash: str):
        return self.registrations_by_hash.get(hash, None)

    def hash_model(self, model: type[models.Model]):
        label = f"{model.__module__}.{model.__name__}"
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    def register(
        self,
        model: type[models.Model],
        base_audit_model: type[models.Model],
        manual_events: list[str] | None,
        list_perm: str,
        parent_model_registrations: list[AuditModelRegistration],
    ):
        # Make sure parents are in order from nearest to furthest parent
        parent_model_registrations = sorted(
            parent_model_registrations,
            reverse=True,
            key=lambda reg: len(model._meta.get_path_to_parent(reg.model)),
        )

        self.registrations[model] = AuditModelRegistration(
            model, manual_events or [], base_audit_model, self, list_perm, parent_model_registrations
        )
        self.registrations_by_hash[self.hash_model(model)] = self.registrations[model]
        # This may get registered multiple times but it doesn't matter, we just use it for the
        # global get_audited_fields method which will be identical across multiple registrations
        _registration_by_model[model] = self.registrations[model]

    def get_registrations_for_user(self, user) -> list[AuditModelRegistration]:
        registrations: list[AuditModelRegistration] = []

        if not user.has_perm(ap_audit_settings.CAN_AUDIT_PERM_NAME):
            return registrations

        for reg in self.registrations.values():
            if user.has_perm(reg.list_perm):
                registrations.append(reg)
        return registrations


default_audit_registry = AuditRegistry()
