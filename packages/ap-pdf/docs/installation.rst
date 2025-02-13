Installation
------------

Install the ``alliance_platform_pdf`` package:

.. code-block:: bash
    poetry add alliance_platform.pdf

Add ``alliance_platform.pdf``, ``alliance_platform.frontend``, and ``alliance_platform.core`` to your ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.core',
        'alliance_platform.frontend',
        'alliance_platform.pdf',
        ...
    ]


Settings
~~~~~~~~

In the settings file:

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.audit.settings import AlliancePlatformAuditSettingsType

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        AUDIT: AlliancePlatformAuditSettingsType
        # Any other settings for alliance_platform packages, e.g. FRONTEND

    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "PDF": {
            "WHITELIST_DOMAINS": [
                "//fonts.googleapis.com",
                "//fonts.gstatic.com",
            ],
        },
    }

Check the :py:attr:`~alliance_platform.pdf.settings.AlliancePlatformPDFSettingsType.WHITELIST_DOMAINS` setting to make sure it contains the required domains for your site. If
you are using external storage like S3 or Azure, and embed images in pages that will be rendered to PDF you should include
the relevant domains here, .e.g. :code:`f"//{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"`.

If you are not serving images from an external domain, you can omit the settings altogether and use the defaults.

Ensure you have your settings for :external:py:class:`alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType`
configured so that the PDFs render properly.
