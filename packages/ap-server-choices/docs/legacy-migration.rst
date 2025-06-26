Legacy Migration
----------------

These instructions can be used to migrate a project using the legacy ``common_lib.server_choices`` package to ``alliance_platform.server_choices``.

The functionality of the package is the same, but the internal structure has been changed slightly.

Install the ``alliance_platform_server_choices`` package as per the :doc:`installation instructions <installation>`.

.. note::

    If this is an older project that is not using the published ``alliance_platform`` packages at all you will need to
    add the following to ``settings/base.py`` (at minimum) if no ``ALLIANCE_PLATFORM`` setting already exists::

        ALLIANCE_PLATFORM = {
            "CORE": {"PROJECT_DIR": PROJECT_DIR},
        }

Follow these steps:

* Delete the ``server_choices`` submodule entirely from ``django-root/common_lib``
* Replace any imports from ``common_lib.server_choices.register`` with imports from ``alliance_platform.server_choices.field_registry``

Custom registration class handlers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your project has added custom subclasses of ``ServerChoiceFieldRegistration`` in your project, and appropriate handling
in ``common_lib.server_choices.__init__.server_choices`` to apply these custom subclasses, you will need
to register those classes in a new registry and ensure they are appropriately applied.

You can check if this is necessary by going to the ``server_choices`` decorator, and checking to see whether it has handling for
only the original registration classes: ``FilterSetServerChoiceFieldRegistration``, ``FormServerChoiceFieldRegistration``, and
``SerializerServerChoiceFieldRegistration``. If only these classes are handled, you can skip this section.

Otherwise, you will need to replicate the custom handling for the registration class by implementing the method
``should_handle_class_for_registration`` on your custom class, which will take the decorated class as an argument and return ``True``
if it is the correct handler for that class.

For example, the following handling for DRF's ``Serializer`` class:

.. code-block:: python

    if issubclass(cls, serializers.Serializer):
        _registration_class = SerializerServerChoiceFieldRegistration
        specialized_kwargs = {"serializer": cls}

Will become:

.. code-block:: python

    class SerializerServerChoiceFieldRegistration(ServerChoiceFieldRegistration):
        ...
        @classmethod
        def should_handle_class_for_registration(cls, decorated_class):
            return issubclass(decorated_class, serializers.Serializer)

.. note::

    The decorated class is no longer passed in ``specialized_kwargs`` - it is now passed automatically to all
    class handlers using the ``decorated_class`` kwarg. If ``specialized_kwargs`` are still needed, raise a ticket
    in the platform repo.

You will then need to make the new class discoverable by importing ``default_class_handler_registry`` from
``alliance_platform.server_choices.class_handlers.registry``, and calling its ``register`` method on the custom class.

Existing registration classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Registration class handlers have been moved to separate modules in a ``class_handlers`` subdirectory. In general
there should not be imports from these modules to other parts of your project, but in case there are you can follow these steps:

* Replace any imports from ``common_lib.server_choices.serializer`` with ``alliance_platform.server_choices.class_handlers.rest_framework``
* Replace any imports of ``common_lib.server_choices.form.FilterSetServerChoiceFieldRegistration`` with
  ``alliance_platform.server_choices.class_handlers.django_filters.FilterSetServerChoiceFieldRegistration``
* Replace any other imports from ``common_lib.server_choices.form``
  with ``alliance_platform.server_choices.class_handlers.form``
