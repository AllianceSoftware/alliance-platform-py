Installation
------------

Install the ``alliance_platform_server_choices`` package:

.. code-block:: bash
    poetry add alliance_platform.server_choices

Add ``alliance_platform.server_choices`` to your ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.server_choices',
        ...
    ]


Settings
~~~~~~~~

In the settings file:

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.server_choices.settings import AlliancePlatformServerChoicesSettingsType

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        SERVER_CHOICES: AlliancePlatformAuditSettingsType
        # Any other settings for alliance_platform packages, e.g. FRONTEND

    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "SERVER_CHOICES": {
            # TODO
        },
    }
