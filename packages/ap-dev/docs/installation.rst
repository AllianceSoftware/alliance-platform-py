Installation
============

Supported platforms are macOS and Linux with Python 3.11 or newer. Projects also require
``uv``, PostgreSQL client tools (``psql``, ``createdb``, and ``dropdb``), ``tmux``, Node.js,
Yarn, and the project-specific Django and Vite commands. Portless is optional unless configured
as required.

From the root of an existing Django project, run the installer from PyPI:

.. code-block:: bash

   uvx --from alliance-platform-dev alliance-dev install

The installer discovers the Django working directory and assumes Vite uses the repository-root
``package.json``. It prints, but does not apply, the development-only Django settings needed by
Portless. Run it from the project root or pass the project path as the final argument. ``--yes``
enables non-interactive defaults. ``--force`` permits replacement of an existing launcher or
project configuration.

The generated ``bin/dev`` launcher pins the installed package version, so every developer and
worktree uses the same release without adding it to the application's Python environment. Commit
both ``bin/dev`` and ``config/dev.toml``.

Post-install setup
------------------

Review the generated command arrays in ``config/dev.toml`` and adjust them to match the project.
In the development settings module, normally ``dev.py``, add the settings printed by the
installer:

.. code-block:: python

   CSRF_TRUSTED_ORIGINS = [
       "https://*.localhost",
       "http://*.localhost",
       "http://localhost",
       "http://127.0.0.1",
   ]

   USE_X_FORWARDED_HOST = True
   SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

These settings trust Portless development origins, preserve the browser hostname used for
subdomain or tenant routing, and tell Django when the original browser request was HTTPS. Keep
them in development settings, where Portless is the trusted proxy.

Then verify the installation and start the environment:

.. code-block:: bash

   bin/dev doctor
   bin/dev up
   bin/dev url

Upgrading
---------

The exact package version in ``bin/dev`` is the project's tool version. Upgrade it deliberately,
review the package changelog, update that pin, and commit the launcher change so the whole team
adopts the release together.
