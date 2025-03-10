from __future__ import annotations

from .form import FormFieldServerChoiceRegistration
from .form import get_form_field_widget

try:
    from django_filters import FilterSet
except ImportError:

    class FilterSet:  # type: ignore [no-redef]
        pass


class FilterSetServerChoiceFieldRegistration(FormFieldServerChoiceRegistration):
    """Registration for FilterSet classes

    As FilterSet uses django Form Fields underneath the only difference is how we extract the
    fields from the ``FilterSet``.

    You usually don't need to instantiate this manually - call :meth:`~alliance_platform.server_choices.server_choices` instead
    """

    def __init__(
        self,
        *,
        decorated_class: type[FilterSet],
        field,
        class_name: str,
        field_name: str,
        perm=None,
        model=None,
        **kwargs,
    ):
        if model is None:
            # a filterset without Meta is useless
            filterset_meta = decorated_class.Meta  # type:ignore[attr-defined]
            assert filterset_meta is not None
            model = filterset_meta.model
        # we have to patch widget here on `base_filters` so applies to any filtersets that
        # are instantiated. In addition, we can't set it directly on `field` otherwise it causes
        # other issues (e.g. `test_server_choices_works_with_modelchoicefilter_callable_querysets` fails
        # as it appears the queryset option is evaluated and cached).
        # Adding it to `extra` then gets used when the field is instantiated.

        # stubs don't pick up that this must exist
        base_filters = decorated_class.base_filters  # type:ignore[attr-defined]
        base_filters[field_name].extra["widget"] = get_form_field_widget(field, self)
        super().__init__(
            field=field,
            class_name=class_name,
            field_name=field_name,
            perm=perm,
            model=model,
            decorated_class=decorated_class,
            **kwargs,
        )

    @classmethod
    def get_available_fields(cls, filterset_cls: type[FilterSet]):
        filterset = filterset_cls()
        return {name: filter.field for name, filter in filterset.filters.items()}

    @classmethod
    def should_handle_class_for_registration(cls, decorated_class):
        return issubclass(decorated_class, FilterSet)
