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

See :doc:`alliance_platform.frontend <alliance-platform-frontend:installation>`
and :doc:`alliance_platform.codegen <alliance-platform-codegen:installation>` for details on installing and configuring the packages
that the UI package depends on.

Ensure that ``FORM_RENDERER`` is be set as follows:

.. code-block:: python

    FORM_RENDERER = "alliance_platform.ui.forms.renderers.FormInputContextRenderer"

This is used by the :ttag:`form` and :ttag:`form_input` tags.

.. _static-form-widgets:

Static form widgets
~~~~~~~~~~~~~~~~~~~

To render Django's text, number and text area widgets as static ``{% ui %}`` components, set
``FORM_RENDERER`` to :class:`~alliance_platform.ui.forms.renderers.StaticFormRenderer` instead:

.. code-block:: python

    FORM_RENDERER = "alliance_platform.ui.forms.renderers.StaticFormRenderer"

It is a ``FormInputContextRenderer``, so the :ttag:`form` and :ttag:`form_input` tags work as before,
and it renders these widgets with templates ap-ui ships, which take the label, help text and
error message :ttag:`form_input` passes:

.. list-table::
    :header-rows: 1
    :widths: 44 38 18

    * - Django widget template
      - ap-ui template
      - Component
    * - ``django/forms/widgets/text.html``, ``email.html``, ``url.html``, ``password.html``,
        ``tel.html`` and ``search.html``
      - ``alliance_platform/ui/widgets/input.html``
      - ``text_input``
    * - ``django/forms/widgets/number.html``
      - ``alliance_platform/ui/widgets/number.html``
      - ``number_input``
    * - ``django/forms/widgets/textarea.html``
      - ``alliance_platform/ui/widgets/textarea.html``
      - ``text_area``

It uses an ap-ui template only where Django's own template would render the widget. A template of
your own for the widget, anywhere in ``TEMPLATES`` and whether it renders a React or a static
component, renders as it would without this renderer, as does a template from a backend other than
Django's. Django's templates for the input widgets above are an ``{% include %}`` of
``django/forms/widgets/input.html``, so your own ``input.html`` counts as a template for each of them;
a project that wrote its own static ``input.html``, ``number.html`` and ``textarea.html`` can delete
them. Every other widget, including the hidden, date, time, checkbox, radio, select and file inputs,
renders as it would with ``FormInputContextRenderer``, so keep your templates for those. To give a
control without a static component the same label, help text and error message, wrap it in
``{% ui "labeled_input" %}`` (see :ref:`static-labeled-inputs`).

Like ``FormInputContextRenderer`` it loads templates through the ``TEMPLATES`` setting, so the app
directories that hold Django's form templates (``django.forms`` in ``INSTALLED_APPS``) and ap-ui's must
be searched.

The ap-ui templates pass a widget's ``attrs`` to the component as props, as the React widget
templates do, so a form sets component props on its widgets. A key takes either spelling, and a
value may be a dict where the component takes one: the ``format_options`` of ``number_input`` render
a Django ``NumberInput`` as a currency input:

.. code-block:: python

    from django import forms


    class ProductForm(forms.ModelForm):
        class Meta:
            model = Product
            fields = ["name", "price"]
            widgets = {
                "price": forms.NumberInput(
                    attrs={"format_options": {"style": "currency", "currency": "AUD"}}
                ),
            }

The number input's runtime formats the value in the browser with those options, and the field still
submits the plain number. Leave ``localize`` off such a field: Django would format the value on the
server in the active locale, which the runtime then parses in its own. The dict must be JSON
serialisable; a value that is not, such as a ``Decimal``, is reported as a contract diagnostic and the
prop is dropped. A prop for one render of a field goes on the :ttag:`form_input` tag instead, such as
``{% form_input form.price addon_before="$" %}``.

Settings
~~~~~~~~

The UI package's own settings are all optional. Set them under ``ALLIANCE_PLATFORM["UI"]``:

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.ui.settings import AlliancePlatformUISettingsType

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        UI: AlliancePlatformUISettingsType
        # Any other settings for alliance_platform packages, e.g. FRONTEND

    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "UI": {"STATIC_COMPONENT_STRICT": False},
    }

.. autoclass:: alliance_platform.ui.settings.AlliancePlatformUISettingsType
    :members:
    :member-order: bysource

``STATIC_COMPONENT_STRICT`` is described under :ref:`static component diagnostics <static-component-diagnostics>`.

.. _static-contract-check:

System checks
-------------

The static ``{% ui %}`` components emit markup for a DOM and CSS contract defined by the
``@alliancesoftware/ui`` and ``@alliancesoftware/icons`` npm packages. Each package records the
version of its side of the contract as an integer ``version`` in a ``static-contract.json`` file at
its root, and each release of ``alliance_platform_ui`` supports one version of each: this release
supports version 1, which ``@alliancesoftware/ui`` ships from 0.0.67 and ``@alliancesoftware/icons``
from 0.0.14. A system check verifies the installed packages, resolving their files through the
bundler as the components do:

.. list-table::
    :header-rows: 1
    :widths: 30 70

    * - Id
      - Reports
    * - ``alliance_platform_ui.E001``
      - ``@alliancesoftware/ui/static-contract.json`` cannot be resolved or read, is not valid JSON
        or has no integer ``version``.
    * - ``alliance_platform_ui.E002``
      - The installed ``@alliancesoftware/ui`` has a different contract version than the supported
        one.
    * - ``alliance_platform_ui.E003``
      - As ``E001``, for ``@alliancesoftware/icons/static-contract.json``.
    * - ``alliance_platform_ui.E004``
      - As ``E002``, for ``@alliancesoftware/icons``.
    * - ``alliance_platform_ui.E005``
      - ``@alliancesoftware/icons/static-svg``, the directory of the static SVG icons, does not
        resolve to a directory.
    * - ``alliance_platform_ui.E006``
      - ``@alliancesoftware/ui/static-runtime.auto.ts``, the static runtime entry, does not resolve
        to a file.

The hint of each error names the first release of the package that ships the supported contract
version. The check runs with Django's other system
checks: in development (``runserver``), with ``manage.py check``, before the tests and before most
other management commands. It is registered with the
:data:`~alliance_platform.frontend.checks.FRONTEND_BUILD_CHECK_TAG` tag, so
:djmanage:`extract_frontend_resources <alliance-platform-frontend:extract_frontend_resources>` runs
it as well, even with ``--skip-checks``, and a production build fails before it starts.

The check is skipped when the directory in the ``NODE_MODULES_DIR`` frontend setting does not
exist, as in a production image after the build, whose run of the check verified the packages, and
while the bundler is not in development mode, as assets then come from the build output.

To silence an error, add its id to Django's ``SILENCED_SYSTEM_CHECKS`` setting. A silenced error
does not fail ``extract_frontend_resources`` either.

.. code-block:: python

    SILENCED_SYSTEM_CHECKS = ["alliance_platform_ui.E002"]

Migration from Alliance Platform Frontend
-----------------------------------------

If you were originally using an older version of ``alliance_platform_frontend`` that incorporated all of the elements of ``alliance_platform_ui``,
you will need to update some settings and templates:

* Change the ``FORM_RENDERER`` Django setting from ``alliance_platform.frontend.forms.renderers.FormInputContextRenderer``
  to ``alliance_platform.ui.forms.renderers.FormInputContextRenderer``

* Find and replace all instances of ``{% load alliance_ui %}`` in your template files with ``{% load alliance_platform.ui %}``

* Find and replace all instances of ``{% load form %}`` in your template files with ``{% load alliance_platform.form %}``
