Installation
------------

Install the ``alliance_platform_codegen`` package:

.. code-block:: bash

    poetry add alliance_platform_codegen

Add ``alliance_platform.codegen`` to your ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.codegen',
        ...
    ]

Configuration
-------------

.. _codegen-configuration:

See the :doc:`settings` documentation for details about each of the available settings.

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.codegen.settings import AlliancePlatformCodegenSettingsType
    # PROJECT_DIR  should be set to the root of your project

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        CODEGEN: AlliancePlatformCodegenSettingsType


    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "CODEGEN": {
            # JS_ROOT_DIR is used to resolve relative paths in the generated code. If not specified, will default to ``PROJECT_DIR``
            "JS_ROOT_DIR": PROJECT_DIR / "frontend",
            # This can be a list of processor instances, or an import path. If an import path, it should be a list of processors.
            # These are used to post-process the generated code at build time. It is not used at runtime.
            "POST_PROCESSORS": "my_project.codegen.post_processors",
        },
    }

See the :ref:`JS post processors <js-post-processors>` for details on using post processors.
