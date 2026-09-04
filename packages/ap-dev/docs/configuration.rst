Configuration
=============

Configuration is merged from lowest to highest precedence:

1. ``<project>/config/dev.toml`` (committed project defaults)
2. ``~/.config/alliance/dev/<project_id>/config.toml`` (user/project overrides)
3. ``<project>/.dev-server/config.toml`` (worktree overrides)

Scalar and argv settings replace lower layers. ``environment`` tables merge by variable name.
``config show`` reports the winning layer for every setting; environment values remain
redacted unless explicitly requested from an interactive terminal. Only the committed layer may
set ``project_id``; the other two layers may override any other setting. Every layer is validated
when the tool starts, and an unknown key or an invalid value in any layer stops every command with
an error naming the file and the key.

Shared environment outside worktrees
------------------------------------

The global layer is project-specific despite living outside the repository. Its directory is
keyed by the committed ``project_id``, so one file supplies machine-local environment values to
the main checkout and every Git worktree for that project:

.. code-block:: bash

   bin/dev config edit global

.. code-block:: toml

   [environment]
   DB_HOST = "localhost"
   SERVICE_API_KEY = "..."

The default path is ``~/.config/alliance/dev/<project_id>/config.toml``. If
``XDG_CONFIG_HOME`` is set, that directory replaces ``~/.config``. ``config edit global`` creates
the file and its parent directories with private permissions. It is not committed and is not
shared with other machines or operating-system users.

This provides the behavior of a project-wide ``.env`` without placing a dotenv file in every
worktree. The syntax is TOML and values belong under ``[environment]``. These values are supplied
to Django, Vite, extra processes, and foreground commands. They are also available to database
control operations. The invoking shell has final precedence, while a worktree-level
``.dev-server/config.toml`` overrides the global layer but remains below the shell.

``bin/dev config paths`` prints the resolved paths for all three layers. ``bin/dev config show``
shows environment names and provenance while redacting their values. In an interactive terminal,
``bin/dev config show --show-environment-values`` displays the effective values.

The repository-root ``.env`` remains separate: ap-dev reads it for PostgreSQL control settings,
and the application may load it through its normal settings machinery. Reserved generated values,
including ``DB_NAME`` and worktree identity/port variables, cannot be configured in any
``[environment]`` table; see :ref:`dev-config-environment` for the full list.

Settings
--------

.. list-table::
   :header-rows: 1
   :widths: 24 56 20

   * - Setting
     - Description
     - Default
   * - ``project_id``
     - Committed lowercase slug (letters, digits, and single hyphens) that identifies the project
       across all of its worktrees. May only be set in ``config/dev.toml``.
     - Required; no default
   * - ``django_port_base``
     - First port considered when allocating a localhost port for Django. Not used while Portless
       assigns the Django port.
     - ``8000``
   * - ``vite_port_base``
     - First port considered when allocating a port for Vite.
     - ``5173``
   * - ``portless``
     - Portless mode: ``auto``, ``off``, or ``required``.
     - ``"auto"``
   * - ``database_template``
     - Existing PostgreSQL database to clone when creating a worktree database. Must not be the
       worktree database itself.
     - ``""`` (disabled)
   * - ``database_template_strategy``
     - PostgreSQL clone strategy: ``default``, ``wal_log``, or ``file_copy``.
     - ``"default"``
   * - ``createdevdata_args``
     - Extra arguments passed to the ``createdevdata`` management command, which runs once when a
       worktree database is created without a template.
     - ``[]``
   * - ``db_prepare_command``
     - Management-command arguments to run once after a worktree database has been created.
     - ``[]`` (disabled)
   * - ``django_cwd``
     - Repository-relative directory containing ``manage.py``. Working directory for
       ``django_command``, ``manage_command``, and ``bin/dev manage``.
     - ``"django-root"``
   * - ``vite_cwd``
     - Repository-relative directory containing the frontend ``package.json``. Working directory
       for ``vite_command`` and for the automatic ``yarn install``.
     - ``"."``
   * - ``verification_virtualenv``
     - Repository-relative virtualenv activated for ``test``, ``lint``, and ``check``. ``""``
       disables activation.
     - ``".venv"``
   * - ``manage_command``
     - Argv prefix for Django management commands: ``bin/dev manage``, migrations,
       ``createdevdata``, and ``db_prepare_command``.
     - ``["uv", "run", "python", "manage.py"]``
   * - ``django_command``
     - Argv that starts the Django development server. The runner appends the bind address; see
       :ref:`dev-config-generated-arguments`.
     - ``["uv", "run", "python", "manage.py", "runserver"]``
   * - ``vite_command``
     - Argv that starts the Vite development server. The runner appends ``--port <port>
       --strictPort``.
     - ``["yarn", "dev"]``
   * - ``test_command``
     - Argv run by ``bin/dev test``. Empty disables the verb.
     - ``[]`` (disabled)
   * - ``jstest_command``
     - Argv run by ``bin/dev jstest``. Empty disables the verb.
     - ``[]`` (disabled)
   * - ``lint_command``
     - Argv run by ``bin/dev lint``. Empty disables the verb.
     - ``[]`` (disabled)
   * - ``check_command``
     - Argv run by ``bin/dev check``. Empty disables the verb.
     - ``[]`` (disabled)
   * - ``startup_timeout``
     - Seconds ``up`` and ``restart`` wait for required processes to become ready.
     - ``60.0``
   * - ``environment``
     - Table of environment variables supplied to managed processes and foreground commands.
     - ``{}``
   * - ``extra_processes``
     - Array of tables describing additional processes to run alongside Django and Vite; see
       :ref:`dev-config-extra-processes`.
     - ``[]``

When ``database_template`` is set, a missing worktree database is cloned from that PostgreSQL
database and ``createdevdata`` is skipped. Migrations still run. ``db_prepare_command`` is a list
of Django management-command arguments that runs only after a new worktree database has been
created. It receives the generated database environment and, when Portless is selected, the
worktree hostname in ``DEV_BASE_HOST``. ``up`` prints and times database cloning, migrations,
development-data creation, and worktree-specific preparation so long-running setup remains
visible.

Command settings are argv arrays and never joined shell strings. ``manage_command``,
``django_command``, and ``vite_command`` must be non-empty. The four verification delegates may
be empty to disable verbs that the project has not configured:

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

Validation rules
~~~~~~~~~~~~~~~~

* Only the settings listed above are accepted; any other key in any layer is an error.
* ``project_id`` must match ``[a-z0-9]+(-[a-z0-9]+)*`` and may appear only in ``config/dev.toml``.
  A project created from the Alliance template must replace the placeholder ``template-django``
  (``bin/dev init-project`` does this); once ``pyproject.toml`` names the real project, a leftover
  template ``project_id`` is rejected with instructions for fixing it.
* ``django_port_base`` and ``vite_port_base`` are integers from 1 to 65535.
* ``portless`` is one of ``"auto"``, ``"off"``, or ``"required"``; ``database_template_strategy``
  is one of ``"default"``, ``"wal_log"``, or ``"file_copy"``.
* Every ``*_command`` setting, ``createdevdata_args``, and ``db_prepare_command`` is an array of
  strings. ``manage_command``, ``django_command``, ``vite_command``, and each extra process
  ``command`` must contain at least one element, and no element may be empty.
* ``django_cwd``, ``vite_cwd``, ``verification_virtualenv``, and each extra process ``cwd`` must
  resolve to a location inside the repository. Working directories must exist when they are used.
* ``startup_timeout`` is a positive number.
* ``environment`` keys must be valid variable names (``[A-Za-z_][A-Za-z0-9_]*``), values must be
  strings, and reserved names are rejected.

.. _dev-config-generated-arguments:

Arguments added by the runner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The configured server commands are argv prefixes; the runner supplies the port-specific arguments so
that every worktree binds differently:

* Without Portless, ``django_command`` receives the bind address ``127.0.0.1:<port>`` as its final
  argument, so it must accept a ``runserver``-style ``address:port`` argument.
* With Portless, the same ``django_command`` runs under ``portless --name
  <worktree-id>.<project_id>`` and receives ``127.0.0.1:$PORT``, where ``PORT`` is assigned by
  Portless. The browser URL is the one Portless reports for that name.
* ``vite_command`` receives ``--port <port> --strictPort``, so it must accept Vite's standard
  options (``yarn dev`` forwards them to ``vite``).
* Extra process commands are started exactly as configured.

.. _dev-config-extra-processes:

Extra processes
~~~~~~~~~~~~~~~

Each ``[[extra_processes]]`` table describes one additional long-running process started by ``up``
alongside Django and Vite:

.. code-block:: toml

   [[extra_processes]]
   name = "worker"
   command = ["uv", "run", "python", "manage.py", "run_worker"]
   cwd = "django-root"
   required = true

.. list-table::
   :header-rows: 1
   :widths: 16 64 20

   * - Key
     - Description
     - Default
   * - ``name``
     - Lowercase slug (``[a-z0-9][a-z0-9-]*``) that names the tmux window and is used as the
       ``TARGET`` of ``restart``, ``logs``, and ``attach``. Must be unique, and cannot be
       ``django``, ``vite``, or ``starting``.
     - Required
   * - ``command``
     - Non-empty argv array. It is executed directly, not through a shell.
     - Required
   * - ``cwd``
     - Repository-relative working directory. Must stay inside the repository and exist at
       startup.
     - ``"."``
   * - ``required``
     - Whether ``up`` waits for this process and fails when it exits. A process with
       ``required = false`` may exit without blocking readiness; its state remains visible in
       ``status`` and its output in ``logs``, and it is not restarted automatically.
     - ``true``

Every extra process receives the same generated environment as Django and Vite, including the
allocated ports and ``DEV_BASE_HOST``; see :ref:`dev-generated-environment`.

.. _dev-config-environment:

Environment
~~~~~~~~~~~

The ``environment`` table supplies non-secret project defaults in committed configuration. Put
private machine-local values in the global layer or use the application's established secret
mechanism. Values are supplied to Django, Vite, extra processes, and every foreground command,
below the invoking shell in precedence, and the generated worktree values are added on top; the
table on the :doc:`commands` page lists exactly which command receives which generated variable.

.. _dev-config-reserved-variables:

Reserved variables
^^^^^^^^^^^^^^^^^^

The runner owns the variables that carry worktree identity. Setting any of them in an
``environment`` table is a configuration error, and the runner replaces or removes a value
exported by the invoking shell whenever it starts a managed process or a foreground command:

* ``DB_NAME`` and ``PGDATABASE``: always the worktree database name;
* ``DEV_PROJECT``, ``DEV_WORKTREE``, and ``DEV_WORKTREE_ID``: always the worktree identity;
* ``DEV_BASE_HOST``, ``DEV_DJANGO_PORT``, and ``DEV_VITE_PORT``: the Portless hostname and
  allocated ports where a command receives them, and otherwise empty or removed.

``VIRTUAL_ENV`` cannot be set in an ``environment`` table either, but a virtualenv active in the
invoking shell is honoured: the verification commands preserve it and only activate
``verification_virtualenv`` when none is active. The launcher's own variables are reserved and
stripped from every process: ``ALLIANCE_DEV_PROJECT_DIR``, ``ALLIANCE_DEV_INVOCATION_NAME``,
``ALLIANCE_DEV_UV_CACHE_DIR``, ``DEV_INVOKE_PATH``, ``DEV_INVOKE_VIRTUAL_ENV``,
``DEV_INVOKE_VIRTUAL_ENV_SET``, ``DEV_INVOKE_UV_RUN_RECURSION_DEPTH``, and
``DEV_INVOKE_UV_RUN_RECURSION_DEPTH_SET``.

Two further variables are adjusted rather than reserved: the repository root is prepended to
``PYTHONPATH``, and ``test``, ``lint``, and ``check`` set ``DISABLE_SSR=1`` regardless of the
shell or configured value. Every other variable from the shell or the ``environment`` tables is
passed through unchanged, with the shell taking precedence.

Because ``DB_NAME`` reaches the application through the process environment, settings code that
loads a ``.env`` file must not let ``.env`` override variables that are already set (python-dotenv's
default); a ``DB_NAME`` in ``.env`` would otherwise defeat worktree isolation.

PostgreSQL control operations (the ``psql``, ``createdb``, and ``dropdb`` invocations the runner
makes itself) use a separate connection environment built from the repository-root ``.env``
(lowest precedence), the ``environment`` tables, and the invoking shell (highest). ``DB_HOST``,
``DB_PORT``, ``DB_USER``, and ``DB_PASSWORD`` are copied to ``PGHOST``, ``PGPORT``, ``PGUSER``, and
``PGPASSWORD`` when the ``PG*`` variable is not already set, and ``PGDATABASE`` is removed so the
operations connect to the server's maintenance database. Application processes do not receive
``.env`` values from the runner; they load ``.env`` through their own settings machinery as usual.

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
the copy. Those checkpoints affect the whole PostgreSQL cluster, but given this is a dev tool this
is mostly fine.

On PostgreSQL 18 or newer, ``FILE_COPY`` can use filesystem copy-on-write cloning when the server
has ``file_copy_method = clone`` and its data directory is on a compatible filesystem. Without
that server setting and filesystem support, ``FILE_COPY`` still performs a regular file copy. See
the PostgreSQL documentation for `CREATE DATABASE strategy
<https://www.postgresql.org/docs/current/sql-createdatabase.html>`_ and
`file_copy_method <https://www.postgresql.org/docs/current/runtime-config-resource.html>`_.
