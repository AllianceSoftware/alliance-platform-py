Installation
------------

Install the ``alliance_platform_ui``, ``alliance_platform_frontend``, and ``alliance_platform_codegen`` packages:

.. code-block:: bash

    poetry add alliance_platform_codegen alliance_platform_frontend alliance_platform_ui

Add ``alliance_platform_ui``, ``alliance_platform.frontend`` and ``alliance_platform.codegen`` to your ``INSTALLED_APPS``:

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.codegen',
        'alliance_platform.frontend',
        'alliance_platform.ui',
        ...
    ]

Configuration
-------------

Currently there are no settings specific to ``alliance_platform_ui``. See :doc:`alliance_platform.frontend <alliance-platform-frontend:installation>`
and :doc:`alliance_platform.codegen <alliance-platform-codegen:installation>` for details on installing and configuring the packages
that the UI package depends on.

Ensure that ``FORM_RENDERER`` is be set as follows:

.. code-block:: python

    FORM_RENDERER = "alliance_platform.ui.forms.renderers.FormInputContextRenderer"

This is used by the :ttag:`form` and :ttag:`form_input` tags.

Migration from Alliance Platform Frontend
-----------------------------------------

If you were originally using an older version of ``alliance_platform_frontend`` that incorporated all of the elements of ``alliance_platform_ui``,
you will need to update some settings and templates:

* Change the ``FORM_RENDERER`` Django setting from ``alliance_platform.frontend.forms.renderers.FormInputContextRenderer``
  to ``alliance_platform.ui.forms.renderers.FormInputContextRenderer``

* Find and replace all instances of ``{% load alliance_ui %}`` in your template files with ``{% load alliance_platform.ui %}``

* Find and replace all instances of ``{% load form %}`` in your template files with ``{% load alliance_platform.form %}``
