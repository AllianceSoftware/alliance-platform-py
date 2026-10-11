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
its root, and each release of ``alliance_platform_ui`` supports one version of each. A system check
verifies the installed packages, resolving their files through the bundler as the components do:

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

The hint of each error names the npm release to install. The check runs with Django's other system
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
