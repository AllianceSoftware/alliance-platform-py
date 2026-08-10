Configuration
=============

Configuration is merged from lowest to highest precedence:

1. ``<project>/config/dev.toml`` (committed project defaults)
2. ``~/.config/alliance/dev/<project_id>/config.toml`` (user/project overrides)
3. ``<project>/.dev-server/config.toml`` (worktree overrides)

Scalar and argv settings replace lower layers. ``environment`` tables merge by variable name.
``config show`` reports the winning layer for every setting; environment values remain
redacted unless explicitly requested from an interactive terminal.

Settings
--------

``project_id`` is a committed lowercase slug. Port allocation uses ``django_port_base`` and
``vite_port_base``. ``portless`` is ``auto``, ``off``, or ``required``. Database setup uses
``database_template``, ``database_template_strategy``, ``createdevdata_args``, and
``db_prepare_command``.

When ``database_template`` is set, a missing worktree database is cloned from that PostgreSQL
database and ``createdevdata`` is skipped. Migrations still run. ``db_prepare_command`` is a list
of Django management-command arguments that runs only after a new worktree database has been
created. It receives the generated database environment and, when Portless is selected, the
worktree hostname in ``DEV_BASE_HOST``. ``up`` prints and times database cloning, migrations,
development-data creation, and worktree-specific preparation so long-running setup remains
visible.

.. _faster-template-database-clones:

Faster template database clones
-------------------------------

By default, the runner lets PostgreSQL select the strategy used to clone ``database_template``.
For a local or otherwise dedicated PostgreSQL server, ``FILE_COPY`` can be selected explicitly:

.. code-block:: toml

   database_template = "my_project_dev_template"
   database_template_strategy = "file_copy"

The supported values are ``default``, ``wal_log``, and ``file_copy``. Non-default values require
PostgreSQL 15 or newer and are passed to ``createdb --strategy``.

``FILE_COPY`` can be much faster for large templates, but it forces a checkpoint before and after
the copy. Those checkpoints affect the whole PostgreSQL cluster, so this strategy is intended for
local or dedicated development servers, not a shared or production-like server.

On PostgreSQL 18 or newer, ``FILE_COPY`` can use filesystem copy-on-write cloning when the server
has ``file_copy_method = clone`` and its data directory is on a compatible filesystem. Without
that server setting and filesystem support, ``FILE_COPY`` still performs a regular file copy. See
the PostgreSQL documentation for `CREATE DATABASE strategy
<https://www.postgresql.org/docs/current/sql-createdatabase.html>`_ and
`file_copy_method <https://www.postgresql.org/docs/current/runtime-config-resource.html>`_.

Project layout and commands are controlled by:

.. code-block:: toml

   django_cwd = "django-root"
   vite_cwd = "."
   verification_virtualenv = ".venv"
   manage_command = ["uv", "run", "python", "manage.py"]
   django_command = ["uv", "run", "python", "manage.py", "runserver"]
   vite_command = ["yarn", "dev"]
   test_command = ["bin/run-tests-django.sh"]
   jstest_command = ["bin/run-tests-frontend.sh"]
   lint_command = ["bin/lint.sh"]
   check_command = ["bin/check.sh"]

Commands are argv arrays and never joined shell strings. ``manage_command``, ``django_command``,
and ``vite_command`` must be non-empty. The four verification delegates may be empty to disable
verbs that the project has not configured:

.. code-block:: toml

   test_command = ["uv", "run", "python", "django-root/manage.py", "test"]
   jstest_command = []
   lint_command = []
   check_command = []

Invoking a disabled verb produces an actionable configuration error. ``doctor`` reports disabled
commands as warnings and validates the entry point of every configured verification command.

``verification_virtualenv`` is the repository-relative Python environment used by ``test``,
``lint``, and ``check`` when the caller has not already activated a virtualenv. The default is
``.venv``. The runner validates ``bin/python``, prepends the virtualenv's ``bin`` directory to
``PATH``, sets ``VIRTUAL_ENV``, and removes ``PYTHONHOME`` before executing the configured project
command. This supports project wrappers that invoke bare tools such as ``coverage`` or ``ruff``.

An explicitly active caller ``VIRTUAL_ENV`` takes precedence and its ``PATH`` and environment are
preserved exactly. Set ``verification_virtualenv = ""`` to disable automatic activation when all
Python verification wrappers manage their own environment with commands such as ``uv run``.
``jstest`` does not activate or require a Python virtualenv, and neither does arbitrary
``bin/dev run`` delegation.

Configured working directories must stay inside the repository and exist when used.
``startup_timeout`` controls readiness. ``extra_processes`` entries contain ``name``, ``command``,
optional ``cwd``, and optional ``required``. The ``environment`` table supplies non-secret project
overrides; application secrets remain in ``.env`` and are loaded only for control/database
operations.

Launcher and generated worktree variables, including ``VIRTUAL_ENV``, are reserved and cannot be
set through the ``environment`` table.
