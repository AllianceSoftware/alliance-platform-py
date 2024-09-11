Alliance Platform
=============================================

.. admonition:: Work in progress

    The platform itself is in use but has some rough edges, and the documentation is currently a work in progress
    and may not be complete. Please bear with us as we continue to improve the platform and its documentation. If you
    are unsure about something or need help, please drop into the ``#alliance-platform2`` channel in Slack.

.. contents::
    :local:

Installation
------------

Alliance Platform is a collection of packages available under the ``alliance_platform`` namespace. Each package can
be installed based on the requirements of the project, with ``alliance_platform_core`` being a common dependency for
all packages.

.. code-block:: bash

    poetry add alliance_platform_core alliance_platform_codegen alliance_platform_frontend

Javascript Packages
-------------------

See the `alliance-platform-js <https://github.com/AllianceSoftware/alliance-platform-js>`_ repository for where the Javascript packages live.

For the UI components, see the `storybook documentation <https://main--64894ae38875dcf46367336f.chromatic.com/>`_.

Configuration
-------------

To configure each package, set the relevant key in the ``ALLIANCE_PLATFORM`` dictionary in your Django settings file.

To include type information for the settings, you can use the following example, noting that you only need to include
the attributes for the packages you are using:

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.codegen.settings import AlliancePlatformCodegenSettingsType
    from alliance_platform.frontend.settings import AlliancePlatformFrontendSettingsType

    class AlliancePlatformSettings(TypedDict):
        # Core should always be included
        CORE: AlliancePlatformCoreSettingsType
        # Include the following if you are using the package
        FRONTEND: AlliancePlatformFrontendSettingsType
        CODEGEN: AlliancePlatformCodegenSettingsType


    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "CODEGEN": {
            # Omitted for brevity
        },
        "FRONTEND": {
            # Omitted for brevity
        },
    }

See the individual package documentation for more information on the available settings.

* :doc:`Core settings <settings>`
* :doc:`Frontend settings <alliance-platform-frontend:settings>`
* :doc:`Codegen settings <alliance-platform-codegen:settings>`

.. toctree::
    :caption: Core
    :maxdepth: 2

    settings
    api

.. include:: _sidebar.rst.inc
