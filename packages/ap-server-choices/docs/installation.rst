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

Register the URL for :class:`~alliance_platform.server_choices.views.ServerChoicesView`. The actual URL path can
be anything you want.

.. code-block:: python

    from alliance_platform.server_choices.views import ServerChoicesView

    urlpatterns = [
        # any other URL patterns
        path("js-api/server-choices/", ServerChoicesView.as_view()),
    ]

To use the default widget you will also need to have `alliance_platform_frontend` installed and setup.

Settings
~~~~~~~~

In the settings file:

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.server_choices.settings import AlliancePlatformServerChoicesSettingsType

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        SERVER_CHOICES: AlliancePlatformServerChoicesSettingsType
        # Any other settings for alliance_platform packages, e.g. FRONTEND

    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "SERVER_CHOICES": {
            "PAGE_SIZE": 20,
        },
    }
