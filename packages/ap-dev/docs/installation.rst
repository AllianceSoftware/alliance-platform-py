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
``package.json``. It retains existing ``bin/run-tests-django.sh``,
``bin/run-tests-frontend.sh``, ``bin/lint.sh``, and ``bin/check.sh`` delegates when present. If
the Django test wrapper is absent, it generates a direct ``manage.py test`` command. It also
recognises package scripts that clearly invoke Vitest and ensures they run once rather than in
watch mode. Ambiguous frontend, lint, and full-check commands are left unconfigured instead of
referencing files that do not exist. Interactive installation prompts for those unresolved
commands; ``--yes`` leaves them disabled for later configuration.

The installer prints, but does not apply, the development-only Django settings needed by
Portless. Run it from the project root or pass the project path as the final argument. ``--yes``
enables non-interactive defaults. ``--force`` permits replacement of an existing launcher or
project configuration.

The generated ``bin/dev`` launcher pins the installed package version, so every developer and
worktree uses the same release without adding it to the application's Python environment. Commit
both ``bin/dev`` and ``config/dev.toml``.

If the project has ``.husky/pre-commit`` or ``.husky/pre-push``, the interactive installer offers
to route their final project command through ``bin/run-with-dev-env-if-managed``. Accept this so
hooks run against the current worktree's generated database and environment whenever that
worktree has been started. Message-only hooks such as ``commit-msg`` and
``prepare-commit-msg`` are left unchanged.

Post-install setup
------------------

Review the verification-command summary and generated arrays in ``config/dev.toml``. An empty
``test_command``, ``jstest_command``, ``lint_command``, or ``check_command`` disables that verb;
invoking it explains which setting to add. ``bin/dev doctor`` reports disabled commands as
warnings and configured entry points that are missing or non-executable as errors.

In the development settings module, normally ``dev.py``, add the settings printed by the installer:

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

Git hooks
---------

The generated hook wrapper checks for ``.dev-server/state.json``. When managed state exists, the
hook command runs through ``bin/dev run`` and receives the worktree database, identity, ports, and
host. Before the first ``bin/dev up``, or in a checkout without managed state, the hook uses the
inherited environment as it did previously.

The wrapper prints which environment it selected. To make one commit or push use the inherited
environment without skipping the hook itself:

.. code-block:: bash

   BIN_DEV_HOOK_ENV=off git commit
   BIN_DEV_HOOK_ENV=off git push

Upgrading
---------

The exact package version in ``bin/dev`` is the project's tool version. Upgrade it deliberately,
review the package changelog, update that pin, and commit the launcher change so the whole team
adopts the release together.
