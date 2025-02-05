Deployment
##########

Heroku
~~~~~~

* Add the https://github.com/Thomas-Boi/heroku-playwright-python-browsers.git buildpack and set `PLAYWRIGHT_BUILDPACK_BROWSERS=chromium` in the Heroku settings.

* Add the https://github.com/playwright-community/heroku-playwright-buildpack buildpack

* ``CHROMIUM_EXECUTABLE_PATH`` can be set to the chromium path if needed. This will be set by the Heroku buildpack automatically. In local dev this isn't necessary.

Note that the chromium executable and dependencies will increase the base slug size.

You can use this sample Aptfile to ensure you have the required package installations for Heroku.

.. code:: bash

    gconf-service
    libappindicator1
    libasound2
    libatk1.0-0
    libatk-bridge2.0-0
    libcairo-gobject2
    libdrm2
    libgbm1
    libgconf-2-4
    libgtk-3-0
    libnspr4
    libnss3
    libx11-xcb1
    libxcb-dri3-0
    libxcomposite1
    libxcursor1
    libxdamage1
    libxfixes3
    libxi6
    libxinerama1
    libxrandr2
    libxshmfence1
    libxss1
    libxtst6
    fonts-liberation
