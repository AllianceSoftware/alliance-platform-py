from __future__ import annotations

from collections.abc import Iterable

from allianceutils.middleware import CurrentRequestMiddleware
from allianceutils.util import camelize
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.forms import BaseForm
from django.forms import Field
from django.forms import Form
from django.forms import ModelChoiceField
from django.forms import ModelForm
from django.forms import Select
from django.forms import SelectMultiple
from django.forms.models import ModelChoiceIterator
from django.forms.widgets import ChoiceWidget
from django.http import HttpRequest
from django.urls import NoReverseMatch
from django.urls import reverse_lazy

from ..field_registry import ServerChoiceFieldRegistration
from ..field_registry import ServerChoiceRecordsType
from ..field_registry import ServerChoiceRecordType
from ..field_registry import ServerChoicesType


def get_form_field_widget(field: Field, registration: ServerChoiceFieldRegistration):
    """Get the form field widget to use on a form field so server choices will work

    This requires either

    a) widget already set explicitly to ServerChoicesSelectWidget or descendant
    b) widget is SelectMultiple or Select

    If neither of these are True then an error will be thrown (e.g. if another widget is
    used that we can't guarantee is compatible with server choices)
    """
    if not isinstance(field.widget, ServerChoicesSelectWidget):
        if not isinstance(field.widget, (Select, SelectMultiple)):
            # TODO: We may need to tweak the logic here more - will see what breaks
            raise ValueError("field.widget must be either Select or SelectMultiple")
        if isinstance(field.widget, SelectMultiple):
            return ServerChoicesSelectMultipleWidget(registration)
        else:
            return ServerChoicesSelectWidget(registration)
    return field.widget


class FormFieldServerChoiceRegistration(ServerChoiceFieldRegistration):
    """Base class for handling django.forms.Field registrations

    Both Form and FilterSet use ``Field`` under the hood so this abstracts away the logic
    for dealing with it. ``get_available_fields`` should be implemented to determine how
    to get the form fields for the class in question.
    """

    def __init__(
        self,
        *,
        field: Field,
        **kwargs,
    ):
        if hasattr(field, "empty_label"):
            kwargs.setdefault("empty_label", field.empty_label)
        super().__init__(field=field, **kwargs)
        field.widget = get_form_field_widget(field, self)

    def get_choices(self, request: HttpRequest) -> ServerChoicesType:
        """Return the available choices for this field. Can return a queryset or list of key/label tuples."""
        if hasattr(self.field, "choices"):
            if isinstance(self.field.choices, ModelChoiceIterator):
                return self.field.queryset
            return self.field.choices
        raise ValueError("Cannot work out choices for field - pass get_choices")

    def get_record(self, pk: str, request: HttpRequest) -> ServerChoiceRecordType:
        """Return the matching record for the specified primary key.

        Raises ObjectDoesNotExist if not found
        """
        choices = self.get_choices(request)
        if isinstance(choices, QuerySet):
            return choices.get(pk=pk)
        for key, value in choices:
            if str(key) == str(pk):
                return (str(key), value)
        raise ObjectDoesNotExist()

    def get_records(self, pks: list[str], request: HttpRequest) -> ServerChoiceRecordsType:
        """Return the matching records for the specified primary keys.

        If any record is not found it is omitted from the return value.
        """
        choices = self.get_choices(request)
        if isinstance(choices, QuerySet):
            return choices.filter(pk__in=pks)
        matches = []
        for key, value in choices:
            if str(key) in [str(x) for x in pks]:
                matches.append((str(key), value))
        return matches

    def serialize(self, item_or_items, request: HttpRequest):
        """Forms always serialize data as strings (eg. from query string)

        Forcing this avoids type mismatches when dealing with data on page load (which is a string)
        vs from the API (which could be an int)"""
        data = super().serialize(item_or_items, request)
        if isinstance(data, list):
            for item in data:
                # It could either be a list of dicts or a list of tuples, eg. [("1", "Item 1")]
                key = 0 if isinstance(item, (list, tuple)) else self.value_field
                item[key] = str(item[key])
        else:
            data[self.value_field] = str(data[self.value_field])
        return data

    @classmethod
    def infer_fields(cls, field_mapping) -> Iterable[str]:
        for field_name, field in field_mapping.items():
            if isinstance(field, ModelChoiceField):
                yield field_name


class FormServerChoiceFieldRegistration(FormFieldServerChoiceRegistration):
    """Registration for django Form classes.

    You usually don't need to instantiate this manually - call :meth:`~alliance_platform.server_choices.server_choices` instead

    Args:
        form: The model class this registration is for
        field: The field on ``form`` this registration is for
        class_name: The registered class name. This is used to index into ``server_choices_registry``.
        field_name: The name of the field
        **kwargs: See :class:`~alliance_platform.server_choices.register.ServerChoiceFieldRegistration`
    """

    def __init__(self, *, decorated_class: type[Form], perm=None, model=None, **kwargs):
        if model is None:
            if issubclass(decorated_class, ModelForm):
                model = decorated_class._meta.model
            elif perm is None:
                raise ValueError("You must specify 'perm' or 'model' when not using a ModelForm")
        super().__init__(perm=perm, model=model, decorated_class=decorated_class, **kwargs)

    @classmethod
    def get_available_fields(cls, form_cls: Form):
        return form_cls.base_fields

    @classmethod
    def should_handle_class_for_registration(cls, decorated_class):
        return issubclass(decorated_class, BaseForm)


class ServerChoicesSelectWidget(Select):
    """Form widget that renders the React ``ServerChoicesSelectWidget`` component

    This widget is attached to fields by FormFieldServerChoiceRegistration - you don't
    need to manually set it.

    See ServerChoicesSelectWidget.tsx for frontend implementation.
    """

    template_name = "alliance_platform/server_choices/widgets/server_choices_select_widget.html"
    server_choice_registration: ServerChoiceFieldRegistration
    input_type = "server-choices"

    def __init__(self, registration: ServerChoiceFieldRegistration, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_choice_registration = registration

    def get_context(self, name, value, attrs):
        context = super(ChoiceWidget, self).get_context(name, value, attrs)
        if self.allow_multiple_selected:
            context["widget"]["attrs"]["multiple"] = True
        try:
            url = reverse_lazy(self.server_choice_registration.registry.attached_view)
        except NoReverseMatch:
            raise ValueError(
                f"ServerChoicesView has not been added for {self.server_choice_registration.registry}. "
                f"Either add the URL or check if the existing URL is namespaced. Namespaced URLs are not supported."
            )
        request = CurrentRequestMiddleware.get_request()
        if value and request:
            # If we have value work out the items for it so the frontend UI can render the labels on load
            # This is then handled by the AsyncChoicesInput.tsx which expects a `initialSelectedItems` prop.
            if isinstance(value, list):
                records: ServerChoiceRecordsType | ServerChoiceRecordType = (
                    self.server_choice_registration.get_records(value, request)
                )
            else:
                records = self.server_choice_registration.get_record(value, request)
            items = self.server_choice_registration.serialize(records, request)
            if not isinstance(items, list):
                items = [items]
            context["initial_selected_items"] = items
        context["server_choices"] = camelize(
            dict(
                api_url=str(url),
                label_field=self.server_choice_registration.label_field,
                value_field=self.server_choice_registration.value_field,
                class_name=self.server_choice_registration.class_name,
                field_name=self.server_choice_registration.field_name,
                is_paginated=self.server_choice_registration.is_paginated(),
                multiple=self.allow_multiple_selected,
                supports_server_search=self.server_choice_registration.supports_server_search,
                source_class_name=self.server_choice_registration.source_class_name,
            )
        )
        return context

    def format_value(self, value):
        if value is None and self.allow_multiple_selected:
            return []
        if not isinstance(value, (tuple, list)):
            return str(value) if value is not None else ""
        return [str(v) if v is not None else "" for v in value]

    # Server Choice selects never uses Optional Group hence we're disabling it here, as otherwise the
    # ChoiceWidget.optgroups causes a full evaluation on the qs prematurely and could lead to performance
    # issue.
    def optgroups(self, *args, **kwargs):
        return []


class ServerChoicesSelectMultipleWidget(ServerChoicesSelectWidget, SelectMultiple):
    """Like ServerChoicesSelectWidget but supports multi-select"""
