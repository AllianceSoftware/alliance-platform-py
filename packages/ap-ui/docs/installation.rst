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

To render Django's text, number, text area, select, checkbox, radio, and
checkbox select multiple widgets as static ``{% ui %}`` components, set
``FORM_RENDERER`` to
:class:`~alliance_platform.ui.forms.renderers.StaticFormRenderer` instead:

.. code-block:: python

    FORM_RENDERER = "alliance_platform.ui.forms.renderers.StaticFormRenderer"

``StaticFormRenderer`` is a ``FormInputContextRenderer``, so the :ttag:`form`
and :ttag:`form_input` tags work as before. Like ``FormInputContextRenderer``,
it loads templates through the ``TEMPLATES`` setting, so ``TEMPLATES`` must
search the app directories that hold Django's form templates (``django.forms``
in ``INSTALLED_APPS``) and ap-ui's.

It renders the widgets that use the Django templates in this table. For each
one, it uses a template that ap-ui ships, which gives the component the label,
help text, and error message that :ttag:`form_input` passes. Django's templates
are under ``django/forms/widgets/``, and the ap-ui templates are under
``alliance_platform/ui/widgets/``:

.. list-table::
    :header-rows: 1
    :widths: 34 34 32

    * - Django template
      - ap-ui template
      - Component
    * - ``text.html``
      - ``input.html``
      - ``text_input``
    * - ``email.html``
      - ``input.html``
      - ``text_input``
    * - ``url.html``
      - ``input.html``
      - ``text_input``
    * - ``password.html``
      - ``input.html``
      - ``text_input``
    * - ``tel.html``
      - ``input.html``
      - ``text_input``
    * - ``search.html``
      - ``input.html``
      - ``text_input``
    * - ``number.html``
      - ``number.html``
      - ``number_input``
    * - ``textarea.html``
      - ``textarea.html``
      - ``text_area``
    * - ``select.html``
      - ``select.html``
      - ``select``
    * - ``checkbox.html``
      - ``checkbox.html``
      - ``checkbox``
    * - ``radio.html``
      - ``radio.html``
      - ``radio_group`` and ``radio``
    * - ``checkbox_select.html``
      - ``checkbox_select.html``
      - ``checkbox_group`` and ``checkbox``

The select, checkbox, radio, and checkbox select widgets render as follows:

* ``Select``, ``SelectMultiple``, and ``NullBooleanSelect`` all use
  ``select.html``, so each one renders as a ``select``.
* ``CheckboxInput`` renders the field's label beside the box, as the React
  ``Checkbox`` widget does. The field's help text, or its errors, render below
  the checkbox.
* ``RadioSelect`` and ``CheckboxSelectMultiple`` render one radio or checkbox
  for each choice, inside a group that has the field's label, help text, and
  error message. The choices of a named group (an optgroup) render in that
  same group, without the group's name.

Every other widget renders as it does with ``FormInputContextRenderer``. That
includes the hidden, date, time, and file inputs, so keep your templates for
those. To give a control that has no static component the same label, help
text, and error message, wrap it in ``{% ui "labeled_input" %}`` (see
:ref:`static-labeled-inputs`).

Your own widget templates
^^^^^^^^^^^^^^^^^^^^^^^^^

``StaticFormRenderer`` uses an ap-ui template only where Django's own template
would render the widget. A template of your own for the widget renders it, as
it does without this renderer. That applies to a template anywhere in
``TEMPLATES``, whether it renders a React or a static component, and to a
template from a backend other than Django's.

Django's widget templates render through other templates, so your own version
of one of those counts as a template for the widget too. For each kind of
widget, these are the templates that count. All of them are under
``django/forms/widgets/``:

* Text, email, URL, password, telephone, search, number, and checkbox inputs:
  the widget's template, such as ``text.html``, or ``input.html``.
* Text areas: ``textarea.html``.
* Selects: ``select.html`` or ``select_option.html``.
* Radio selects: ``radio.html``, ``multiple_input.html``,
  ``radio_option.html``, ``input_option.html``, or ``input.html``.
* Checkbox selects: ``checkbox_select.html``, ``multiple_input.html``,
  ``checkbox_option.html``, ``input_option.html``, or ``input.html``.

If your project has its own static ``input.html``, ``number.html``, and
``textarea.html``, you can delete them and use the ap-ui templates.

The ap-ui select template writes each ``<option>`` itself. If a widget class
sets an ``option_template_name`` of its own, the ap-ui template renders each
option with that template instead.

Component props on widgets
^^^^^^^^^^^^^^^^^^^^^^^^^^

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
its root, and each release of ``alliance_platform_ui`` supports one version of each. This release
supports these versions:

.. list-table::
    :header-rows: 1
    :widths: 40 25 35

    * - Package
      - Contract version
      - First release that ships it
    * - ``@alliancesoftware/ui``
      - 2
      - 0.0.68
    * - ``@alliancesoftware/icons``
      - 1
      - 0.0.14

A system check verifies the installed packages, resolving their files through the bundler as the
components do:

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
