from __future__ import annotations

from ..field_registry import ServerChoiceFieldRegistration


class ClassHandlerRegistry:
    """Registry for handlers for classes which can be decorated using :meth:`~alliance_platform.server_choices.decorators.server_choices`.

    A default registry is instantiated that supports Django forms, as well as DRF serializers and django-filter
    FilterSets if available. New classes can be supported by importing the default registry and calling
    :meth:`~alliance_platform.server_choices.class_handlers.registry.ClassHandlerRegistry.register`.

    Checking the registry can be bypassed by passing ``registration_class`` directly to the ``server_choices`` decorator.
    """

    # This is for easy lookup by class itself and field name.
    registered_handlers: list[type[ServerChoiceFieldRegistration]]

    def __init__(self, name):
        """
        Args:
            name: A name for this registration. This is just used to make debugging easier when printing out registration instances.
        """
        self.name = name
        self.registered_handlers = []
        self.server_choices_registry = {}

    def __str__(self):
        return f"ServerChoicesRegistry(name='{self.name}')"

    def register(self, class_handler: type[ServerChoiceFieldRegistration]):
        """Add a handler to the list of backends which are looked up to handle decorated classes.
        Note that class handlers are checked in reverse order, and checking stops when a suitable class
        is found. This is based on the idea that devs will be registering their own class handlers
        after the default handlers, and will want theirs to take priority.
        """
        if class_handler not in self.registered_handlers:
            self.registered_handlers.append(class_handler)


default_class_handler_registry = ClassHandlerRegistry("default")

from .form import FormServerChoiceFieldRegistration  # noqa: E402

default_class_handler_registry.register(FormServerChoiceFieldRegistration)
try:
    from .rest_framework import SerializerServerChoiceFieldRegistration  # noqa: E402

    default_class_handler_registry.register(SerializerServerChoiceFieldRegistration)
except ImportError:
    pass

try:
    from .django_filters import FilterSetServerChoiceFieldRegistration  # noqa: E402

    default_class_handler_registry.register(FilterSetServerChoiceFieldRegistration)
except ImportError:
    pass
