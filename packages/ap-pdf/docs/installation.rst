Installation
------------

Install the ``alliance_platform.pdf`` package:

.. code-block:: bash
    poetry add alliance_platform.pdf

Add ``alliance_platform.pdf`` to your ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.pdf',
        ...
    ]

Heroku
~~~~~~

* Add the https://github.com/Thomas-Boi/heroku-playwright-python-browsers.git buildpack and set `PLAYWRIGHT_BUILDPACK_BROWSERS=chromium` in the Heroku settings.

* Add the https://github.com/playwright-community/heroku-playwright-buildpack buildpack

* ``CHROMIUM_EXECUTABLE_PATH`` can be set to the chromium path if needed. This will be set by the Heroku buildpack automatically. In local dev this isn't necessary.

Note that the chromium executable and dependencies will increase the base slug size.


Settings
~~~~~~~~

Check the :code:`ALLIANCE_PLATFORM_PDF_WHITELIST_DOMAINS` setting to make sure it contains the required domains for your site. If
you are using external storage like S3 or Azure, and embed images in pages that will be rendered to PDF you should include
the relevant domains here, .e.g. :code:`f"//{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"`.
