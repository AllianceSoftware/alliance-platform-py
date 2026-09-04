Installation
============

These instructions target macOS and assume an existing Git repository containing a Django and
Vite project. ``alliance-platform-dev`` requires Python 3.11 or newer; ``uv`` can download a
compatible Python automatically when necessary.

Prerequisites
-------------

The runner checks its dependencies with ``bin/dev doctor`` after it has been installed.

.. list-table::
   :header-rows: 1
   :widths: 18 16 66

   * - Dependency
     - Requirement
     - Purpose
   * - ``uv``
     - Required
     - Runs the pinned ``alliance-platform-dev`` release and provisions the project environment.
   * - PostgreSQL
     - Required
     - Use `Postgres.app <https://postgresapp.com/>`_ on macOS rather than a Homebrew-managed
       PostgreSQL installation.
   * - ``tmux``
     - Required
     - Hosts Django, Vite, and extra processes in a worktree-specific background session.
   * - Node.js and Yarn
     - Required
     - Run Vite and install frontend dependencies. Use the Node.js version selected by the
       project; the standard project template uses Node.js 20.
   * - Portless
     - Optional
     - Provides stable HTTPS ``*.localhost`` URLs. Without it, Django remains available on an
       allocated ``http://localhost:<port>`` URL.

Install ``uv`` by following the `official installation instructions
<https://docs.astral.sh/uv/getting-started/installation/>`_. Install ``tmux`` with
`Homebrew <https://brew.sh/>`_:

.. code-block:: bash

   brew install tmux

Confirm that ``tmux`` is available:

.. code-block:: bash

   tmux -V

Use the project's existing Node.js version manager. For a project with an ``.nvmrc`` file, for
example:

.. code-block:: bash

   nvm install
   nvm use
   corepack enable
   node --version
   yarn --version

Optional: install Portless
--------------------------

Install Portless globally after Node.js is available:

.. code-block:: bash

   npm install --global portless
   portless trust

To start the proxy

.. code-block:: bash

    portless proxy start --https --wildcard

``--wildcard`` can be useful if you have multi-tenant setup where different tenants get a different subdomain.

Portless creates and trusts a local certificate authority and runs its HTTPS proxy on port 443,
so macOS may request administrator approval unless you explicitly use an unprivileged port with the ``--port`` option.

The default ``portless = "auto"`` policy uses Portless when a compatible CLI is installed and
otherwise falls back to allocated localhost ports. Set it to ``"off"`` when the project should
never use Portless, or ``"required"`` when startup should fail rather than fall back. See
:doc:`configuration` for the full setting reference.

Install into a project
----------------------

From the root of an existing Django project, run the installer from PyPI:

.. code-block:: bash

   uvx --from alliance-platform-dev alliance-dev install

The installer discovers the Django working directory and assumes Vite uses the repository-root
``package.json``. It retains existing executable ``bin/run-tests-django.sh``,
``bin/run-tests-frontend.sh``, ``bin/lint.sh``, and ``bin/check.sh`` delegates when present. If
the Django test wrapper is absent, it generates a direct ``manage.py test`` command. It also
recognises package scripts that clearly invoke Vitest and ensures they run once rather than in
watch mode. Ambiguous frontend, lint, and full-check commands are left unconfigured instead of
referencing files that do not exist. Interactive installation prompts for those unresolved
commands; ``--yes`` leaves them disabled for later configuration.

The installer prints, but does not apply, the development-only Django settings needed by
Portless. Run it from the project root or pass the project path as the final argument. ``--yes``
enables non-interactive defaults. ``--force`` permits replacement of an existing launcher or
project configuration. ``--django-cwd`` names the directory containing ``manage.py`` when
discovery would choose the wrong one, and ``--tool-source`` writes a different package source
into the launcher, for example a pre-release. See :ref:`dev-command-install` for every option.

The generated ``bin/dev`` launcher pins the installed package version, so every developer and
worktree uses the same release without adding it to the application's Python environment. Commit
both ``bin/dev`` and ``config/dev.toml``. Also make sure ``.dev-server/`` is listed in
``.gitignore``: the runner keeps worktree state, output snapshots, and the optional worktree
configuration layer there, and the installer does not edit ``.gitignore``.

If the project has ``.husky/pre-commit`` or ``.husky/pre-push``, the interactive installer offers
to route their final project command through ``bin/run-with-dev-env-if-managed``; with ``--yes``
the hooks are updated without prompting. Accept this so hooks run against the current worktree's
generated database and environment whenever that worktree has been started. Message-only hooks
such as ``commit-msg`` and ``prepare-commit-msg`` are left unchanged, and a hook whose final
command cannot be wrapped safely is reported so it can be updated by hand.

Configure and start the project
-------------------------------

Review the verification-command summary and generated arrays in ``config/dev.toml``. An empty
``test_command``, ``jstest_command``, ``lint_command``, or ``check_command`` disables that verb;
invoking it explains which setting to add. ``bin/dev doctor`` reports disabled commands as
warnings and configured entry points that are missing or non-executable as errors. The generated
``verification_virtualenv = ".venv"`` setting makes Python-backed ``test``, ``lint``, and ``check``
commands work without manually sourcing ``.venv/bin/activate`` after dependencies are provisioned
with ``uv sync``. An intentionally active caller virtualenv still takes precedence.

When using Portless, add the settings printed by the installer to the development settings module,
normally ``dev.py``:

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

Provision the project dependencies, verify the complete setup, and start the environment:

.. code-block:: bash

   uv sync
   bin/dev doctor
   bin/dev up
   bin/dev url

The first uncached ``bin/dev`` invocation needs network access to obtain the pinned tool release.
``doctor`` reports missing required tools as errors and a missing optional Portless installation as
a warning when the policy is ``"auto"``.

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

Launcher implementation notes
-----------------------------

Most users do not need to configure the launcher. It runs the pinned tool through an isolated
``uvx`` environment and keeps a user-scoped cache under
``${TMPDIR:-/tmp}/alliance-dev-$UID/uv-cache``. The operating system may eventually clear that
cache, in which case the next invocation downloads the tool again. Set
``ALLIANCE_DEV_UV_CACHE_DIR`` to override this location; the standard ``UV_CACHE_DIR`` is used when
the launcher-specific variable is unset.

For package development, a local path or ``file://`` source supplied through
``ALLIANCE_DEV_TOOL_SOURCE`` is loaded as an isolated editable installation so uncommitted source
changes are visible. The launcher probes an already provisioned local environment offline and
only retries online when a required build or runtime artifact is missing. Git and PyPI sources use
normal ``uvx`` caching; use an immutable Git revision when reproducibility matters.
