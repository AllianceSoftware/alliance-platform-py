Commands
========

Every command is normally run through the project's checked-in launcher, ``bin/dev``. The launcher
runs the pinned ``alliance-platform-dev`` release with ``uvx`` and exposes the same command-line
interface as the ``alliance-dev`` console script and ``python -m alliance_platform.dev``. Examples
on this page use ``bin/dev``.

Invocation
----------

.. code-block:: text

   bin/dev [--project-dir PATH] COMMAND [OPTIONS] [ARGUMENTS]
   bin/dev help [COMMAND]
   bin/dev --version

Every command except ``--version``, ``--help``, ``help``, and ``install`` operates on one project.
The project root is, in order of precedence: the ``--project-dir`` option, the
``ALLIANCE_DEV_PROJECT_DIR`` environment variable (the ``bin/dev`` launcher sets it to the
repository that contains the launcher), or the nearest directory at or above the current directory
that contains both ``config/dev.toml`` and ``pyproject.toml``. Because the launcher pins the
project, ``bin/dev`` works from any subdirectory of a worktree, and the ``bin/dev`` of one worktree
never operates on another.

.. program:: bin/dev

.. option:: --project-dir PATH

   Operate on the project at ``PATH``, which must contain ``config/dev.toml`` and
   ``pyproject.toml``. This option must appear before the command name. It overrides
   ``ALLIANCE_DEV_PROJECT_DIR``.

.. option:: --version

   Print the package version and the development protocol version, for example
   ``alliance-platform-dev 0.0.2 (development protocol 1)``, and exit. No project is required.

.. option:: -h, --help

   Print the top-level usage and the list of commands. Running ``bin/dev`` with no arguments does
   the same. No project is required.

``bin/dev help COMMAND`` prints the usage of one command and exits. It is the only way to see the
wrapper's own usage for ``manage``, ``test``, ``jstest``, ``lint``, and ``check``, because those
commands forward every argument, including ``--help``, to the underlying tool.

Quick reference
---------------

.. list-table::
   :header-rows: 1
   :widths: 20 36 44

   * - Command
     - Arguments
     - Purpose
   * - :ref:`up <dev-command-up>`
     - ``[--no-portless]``
     - Start this worktree's environment, or confirm that it is already running.
   * - :ref:`down <dev-command-down>`
     - ``[--drop-db] [--yes]``
     - Stop this worktree's processes, optionally dropping its database.
   * - :ref:`restart <dev-command-restart>`
     - ``[TARGET]``
     - Restart every process or one named process.
   * - :ref:`status <dev-command-status>`
     - ``[--all] [--json]``
     - Show process health, readiness, URLs, and database for this or every active worktree.
   * - :ref:`logs <dev-command-logs>`
     - ``[TARGET] [--lines N]``
     - Print recent output from the running processes or the last saved snapshot.
   * - :ref:`attach <dev-command-attach>`
     - ``[TARGET]``
     - Attach a tmux client to the session.
   * - :ref:`url <dev-command-url>`
     - ``[--json]``
     - Print the Django URL once the environment is ready.
   * - :ref:`doctor <dev-command-doctor>`
     - ``[--json]``
     - Diagnose tools, PostgreSQL, tmux, Portless, and verification commands.
   * - :ref:`env list <dev-command-env-list>`
     - ``[--json]``
     - List every registered environment for the project, including stopped ones.
   * - :ref:`env remove <dev-command-env-remove>`
     - ``ENVIRONMENT-ID [--yes]``
     - Stop, drop, and forget one registered environment.
   * - :ref:`manage <dev-command-manage>`
     - ``COMMAND [ARGS...]``
     - Run a Django management command against the worktree database.
   * - :ref:`test <dev-command-verification>`
     - ``[ARGS...]``
     - Run the configured Django test command.
   * - :ref:`jstest <dev-command-verification>`
     - ``[ARGS...]``
     - Run the configured frontend test command.
   * - :ref:`lint <dev-command-verification>`
     - ``[ARGS...]``
     - Run the configured lint command.
   * - :ref:`check <dev-command-verification>`
     - ``[ARGS...]``
     - Run the configured full local check.
   * - :ref:`run <dev-command-run>`
     - ``[--cwd PATH] -- COMMAND [ARGS...]``
     - Run any command with the worktree environment.
   * - :ref:`config show <dev-command-config-show>`
     - ``[--json] [--show-environment-values]``
     - Show effective settings and which layer supplied each one.
   * - :ref:`config paths <dev-command-config-paths>`
     - ``[--json]``
     - Show the path of every configuration layer.
   * - :ref:`config edit <dev-command-config-edit>`
     - ``LAYER``
     - Open a configuration layer in ``$EDITOR``.
   * - :ref:`install <dev-command-install>`
     - ``[PATH] [--yes] [--force] [--django-cwd DIR] [--tool-source SOURCE]``
     - Add ``bin/dev`` and ``config/dev.toml`` to an existing Django project.
   * - :ref:`init-project <dev-command-init-project>`
     - ``REPOSITORY-NAME``
     - Replace the template project identity in a newly created project.
   * - ``help``
     - ``[COMMAND]``
     - Print usage for the tool or for one command.

Lifecycle commands
------------------

.. _dev-command-up:

``up``
~~~~~~

.. program:: bin/dev up

.. code-block:: bash

   bin/dev up [--no-portless]

Starts this worktree's environment, or confirms that it is already running. ``up`` is idempotent:
when the session exists and every required process is alive and ready, it reports ``dev environment
already running`` with the current URLs and exits successfully. When the session exists but a
required process has exited or is not answering, ``up`` fails and points at ``logs``.

A fresh start performs these steps in order, printing a progress line for each one that takes
time:

1. **Preflight.** Refuses to start while a different session for this worktree is active, requires
   ``psql``, ``createdb``, and a ``dropdb`` that supports ``--force``, and removes a database left
   behind by a previously interrupted start.
2. **Node.js and frontend dependencies.** When ``.nvmrc`` names a Node.js major version that is
   not the active ``node``, the matching ``nvm`` installation is placed on ``PATH``; the command
   fails if ``nvm`` or that version cannot be found. ``yarn install`` (with ``--immutable`` when
   ``yarn.lock`` exists) then runs in ``vite_cwd`` if ``node_modules`` is missing, is a symlink
   (which is removed first), or is older than ``package.json``, ``yarn.lock``, or ``.yarnrc.yml``.
3. **Portless selection.** Applies the ``portless`` policy from the configuration, unless
   ``--no-portless`` forces localhost ports.
4. **Database.** Creates the worktree database when it does not exist, by cloning
   ``database_template`` when one is configured and otherwise with ``createdb``. Runs
   ``migrate --noinput`` on every start. Only when the database was just created, runs
   ``createdevdata`` (skipped when a template was cloned) and then ``db_prepare_command``.
5. **Ports and processes.** Allocates the Django and Vite ports, reusing the worktree's previous
   ports when they are still free, and starts Django, Vite, and every ``extra_processes`` entry in
   the worktree's tmux session.
6. **Readiness.** Waits up to ``startup_timeout`` seconds for Vite to answer on its port for this
   worktree and for the Django URL to respond (see :doc:`architecture`). A required process that
   exits during the wait fails the start.

When a fresh start fails, ``up`` saves each process's output under ``.dev-server/logs/``, stops the
partial session, and drops a database that this run created, so the next ``up`` begins from a clean
state. On success it prints the branch, worktree ID, database name, and URLs, followed by
``Ready.``; when Portless is not in use it also prints the reason.

.. option:: --no-portless

   Use an allocated ``http://localhost:<port>`` URL for this start even when Portless is installed
   and the policy is ``auto`` or ``required``. The override lasts until the next ``up`` or
   ``restart``, both of which re-evaluate the configured policy.

.. _dev-command-down:

``down``
~~~~~~~~

.. program:: bin/dev down

.. code-block:: bash

   bin/dev down [--drop-db [--yes]]

Stops this worktree's processes. The last 1000 lines of each process's output are saved to
``.dev-server/logs/<process>.log`` so that ``logs`` keeps working afterwards; each live process is
then interrupted and the tmux session is killed. The database and the recorded port assignments
are kept, so the next ``up`` reuses them. ``down`` succeeds when nothing is running.

When a previous ``up`` was interrupted while creating the database, ``down`` also removes that
incomplete database and its registry record, without needing ``--drop-db``.

.. option:: --drop-db

   Also drop this worktree's PostgreSQL database and remove its record from the machine-wide
   registry. In an interactive terminal the command prints the database name and requires it to be
   typed back. It refuses to drop the database while another session for the same worktree is
   active.

.. option:: --yes

   Skip the confirmation prompt. Required together with ``--drop-db`` when stdin or stdout is not
   a terminal, for example from scripts and agents.

.. _dev-command-restart:

``restart``
~~~~~~~~~~~

.. program:: bin/dev restart

.. code-block:: bash

   bin/dev restart [TARGET]

Restarts the running environment. It fails, with a hint to run ``up``, when the environment is not
running or its database setup is incomplete. Like ``up``, it activates the Node.js version named by
``.nvmrc`` before starting processes.

.. option:: TARGET

   ``all`` (the default) stops every process, re-applies the configured Portless policy,
   re-allocates ports (reusing the previous ones when still free), relaunches everything, and waits
   for readiness exactly as ``up`` does. Frontend dependencies and the database are not re-checked.

   A process name (``django``, ``vite``, or the ``name`` of an ``extra_processes`` entry) restarts
   only that process in place. Restarting ``django`` or ``vite`` waits for readiness again; any
   other process is checked to still be running shortly after it is relaunched. The command fails
   before doing anything if another required process has already exited.

.. _dev-command-status:

``status``
~~~~~~~~~~

.. program:: bin/dev status

.. code-block:: bash

   bin/dev status [--all] [--json]

Reports the tmux session, per-process state, readiness, URLs, and database name. Without ``--all``
it describes this worktree and actively probes readiness. ``status`` exits ``0`` even when nothing
is running: the current worktree is then reported with an ``absent`` session, and ``--all`` prints
``No active dev environments``.

Text output shows one block per environment: the session name with its branch, session state, and
readiness in parentheses, followed by the worktree path, URLs, database name, and a ``failures``
line naming any process that is not running.

.. option:: --all

   List every active session for this project across all of its worktrees. Readiness is not probed
   in this mode and is reported as ``notProbed``. Compare with ``env list``, which reads the
   registry and therefore also shows stopped environments.

.. option:: --json

   Print a single JSON document instead of text. Without ``--all`` the record is under
   ``environment``; with ``--all`` a list of records is under ``environments``.

   .. code-block:: json

      {
        "schemaVersion": 1,
        "environment": {
          "projectId": "my-project",
          "worktree": {
            "id": "my-project-billing-1a2b3c4d5e",
            "path": "/work/my-project-billing",
            "branch": "feature/billing"
          },
          "session": {"name": "my-project-wt-my-project-billing-1a2b3c4d5e", "state": "running"},
          "readiness": "ready",
          "databaseName": "my_project_my_project_billing_1a2b3c4d5e",
          "urls": {
            "django": "https://my-project-billing-1a2b3c4d5e.my-project.localhost",
            "vite": "http://localhost:5173"
          },
          "processes": [
            {"name": "django", "required": true, "state": "running", "exitCode": null, "signal": null},
            {"name": "vite", "required": true, "state": "running", "exitCode": null, "signal": null},
            {"name": "worker", "required": false, "state": "exited", "exitCode": 1, "signal": null}
          ]
        }
      }

   ``session.state`` is ``running``, ``degraded`` (at least one process is not running), or
   ``absent``. ``readiness`` is ``ready``, ``notReady``, or ``notProbed``. Each process ``state``
   is ``running``, ``exited``, or ``missing``. URLs are ``null`` when unknown. For worktrees other
   than the current one, ``required`` is ``null`` for extra processes because their configuration
   is not read.

.. _dev-command-logs:

``logs``
~~~~~~~~

.. program:: bin/dev logs

.. code-block:: bash

   bin/dev logs [TARGET] [--lines N]

Prints recent process output. While the session is running, output is captured live from each tmux
pane. Otherwise the snapshot saved by the last ``down``, failed start, or process restart is used.
The command fails when no output is available at all. There is no follow mode; use ``attach`` to
watch output live.

.. option:: TARGET

   A process name: ``django``, ``vite``, or the ``name`` of an ``extra_processes`` entry.
   Without it, every process is printed in turn under a ``━━━ <name> (last N lines) ━━━``
   heading.

.. option:: --lines N

   Number of lines per process. Defaults to 200 for a single target and 50 when every process is
   shown. Must be positive. Saved snapshots hold at most the last 1000 lines.

.. _dev-command-attach:

``attach``
~~~~~~~~~~

.. program:: bin/dev attach

.. code-block:: bash

   bin/dev attach [TARGET]

Replaces the current process with a tmux client attached to this worktree's session. It requires a
running environment and an interactive terminal. Each process runs in a tmux window named after
it. The session lives on a dedicated tmux server (socket name ``alliance-dev-v1``) that is started
without a user configuration file, so the default tmux key bindings apply: ``Ctrl-b d`` detaches,
and ``Ctrl-b n`` / ``Ctrl-b p`` move between windows. Detach rather than closing windows; the
runner expects every window to remain in place so that ``restart`` and ``logs`` can find it.

.. option:: TARGET

   Attach with the named process's window selected.

.. _dev-command-url:

``url``
~~~~~~~

.. program:: bin/dev url

.. code-block:: bash

   bin/dev url [--json]

Prints the Django URL for this worktree: the Portless URL when Portless is in use, otherwise
``http://localhost:<port>``. The command fails when the environment is not running or not yet
ready, so scripts can rely on the printed URL being live.

.. option:: --json

   Print ``{"schemaVersion": 1, "url": "..."}`` instead of the bare URL.

.. _dev-command-doctor:

``doctor``
~~~~~~~~~~

.. program:: bin/dev doctor

.. code-block:: bash

   bin/dev doctor [--json]

Prints the tool and protocol versions, the worktree identity (branch, worktree ID, database name,
and tmux session name), the state of ``.dev-server/state.json`` (``missing``, ``valid``, or
``invalid``), and a list of checks. Each check is ``ok``, ``warning``, or ``error``, and the text
output ends with a summary line such as ``2 errors, 1 warning.`` ``doctor`` changes nothing. It
exits ``1`` when any check is an ``error`` and ``0`` otherwise; warnings do not affect the exit
status.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Check
     - Meaning
   * - ``tool:uv``, ``tool:node``, ``tool:yarn``, ``tool:tmux``, ``tool:psql``, ``tool:createdb``,
       ``tool:dropdb``
     - The executable is on ``PATH``; ``error`` when missing.
   * - ``tool:portless``
     - The optional Portless CLI is on ``PATH``; ``warning`` when missing.
   * - ``verification:virtualenv``
     - The virtualenv that ``test``, ``lint``, and ``check`` will use: ``ok`` when the caller's
       active virtualenv or the configured ``verification_virtualenv`` is provisioned, ``warning``
       when automatic activation is disabled, ``error`` when it is missing, and ``ok`` (not
       required) when none of those commands is configured.
   * - ``command:test``, ``command:jstest``, ``command:lint``, ``command:check``
     - ``warning`` when the verb is not configured; otherwise ``error`` unless the first argv
       element is an existing executable file (for paths) or is found on ``PATH`` (for bare
       names).
   * - ``dropdb:force``
     - The installed ``dropdb`` supports ``--force``, which the runner relies on to remove
       databases safely.
   * - ``tmux:backend``
     - ``tmux`` is available; the detail names the socket and counts managed sessions.
   * - ``postgres:connectivity``
     - ``psql`` can query the server using the current connection settings, without creating or
       changing databases.
   * - ``portless``
     - Outcome of the configured policy: ``error`` when ``required`` cannot be satisfied,
       ``warning`` when ``auto`` will fall back to localhost, otherwise ``ok``.

.. option:: --json

   Print a JSON document with ``schemaVersion``, ``tool`` (``version`` and ``protocolVersion``),
   ``identity`` (``projectId``, ``worktreeId``, ``worktreePath``, ``databaseName``,
   ``sessionName``), ``configPaths`` (the same records as ``config paths --json``), ``state``
   (``path``, ``status``, ``databaseSetupPending``), and ``checks`` (a list of ``name``,
   ``status``, ``detail``).

Registered environment commands
-------------------------------

The runner keeps a machine-wide registry of every environment it has started, under
``$XDG_STATE_HOME/alliance/dev/registry/v1`` (normally ``~/.local/state/alliance/dev/registry/v1``).
These commands read and clean up that registry for the current project. See :doc:`architecture`
for what the registry records.

.. _dev-command-env-list:

``env list``
~~~~~~~~~~~~

.. program:: bin/dev env list

.. code-block:: bash

   bin/dev env list [--json]

Lists every environment recorded for this project, including stopped ones and ones whose worktree
directory has since been deleted. Each entry shows the environment ID (which is the worktree ID),
its state, branch, worktree path, tmux session and session state, database name with whether it is
present and whether the runner owns it, owner, and when it was last seen.

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - State
     - Meaning
   * - ``running``
     - The session is alive and the worktree directory exists.
   * - ``running-orphaned``
     - The session is alive but the worktree directory has been removed.
   * - ``stopped``
     - No session; the worktree directory exists. The database may still be retained.
   * - ``orphaned``
     - No session and the worktree directory has been removed. Use ``env remove`` to release its
       database.
   * - ``incomplete``
     - Database setup was interrupted. Running ``up`` in that worktree recovers it.
   * - ``conflict``
     - A tmux session with the registered name exists but its metadata does not match the
       registry entry. Inspect it before removing anything.

.. option:: --json

   Print ``{"schemaVersion": 1, "environments": [...]}``. Each record contains ``id``, ``state``,
   ``projectId``, ``worktree`` (``path``, ``branch``, ``exists``), ``session`` (``name``,
   ``state``), ``database`` (``name``, ``present``, ``owned``, ``setupPending``), ``owner``
   (``kind``, ``id``, ``leaseExpiresAt``), and ``activity`` (``registeredAt``, ``lastSeenAt``,
   ``lastStartedAt``, ``lastStoppedAt``).

.. _dev-command-env-remove:

``env remove``
~~~~~~~~~~~~~~

.. program:: bin/dev env remove

.. code-block:: bash

   bin/dev env remove ENVIRONMENT-ID [--yes]

Removes one registered environment. The command stops its tmux session when one is running (after
verifying that the session's metadata matches the registry entry), drops its database only when the
registry records that the runner created that database, and then deletes the registry record.
Databases that the runner did not create are always retained. Before making any change, the
command verifies that the registered database and session names are the deterministic names
derived from the environment ID, and refuses to continue otherwise.

.. option:: ENVIRONMENT-ID

   The exact ID printed by ``env list``.

.. option:: --yes

   Skip confirmation. Interactively, the command shows the affected worktree, session, and
   database and requires the environment ID to be typed back. Required when stdin or stdout is not
   a terminal.

Foreground commands
-------------------

Foreground commands run project tooling with this worktree's generated environment, so a command
run from one worktree cannot silently use another worktree's database. ``test``, ``jstest``,
``lint``, ``check``, and ``run`` replace the runner process with the target command, so the exit
status, standard streams, and signals are the command's own. ``manage`` runs the management command
as a child process and exits with its status.

Before the target starts, the ``PATH`` and ``VIRTUAL_ENV`` that the ``bin/dev`` launcher's isolated
``uvx`` environment introduced are removed, restoring the caller's shell environment. The generated
values below are then added on top. Everything after ``manage``, ``test``, ``jstest``, ``lint``, or
``check`` is passed to the underlying command verbatim, including ``--help``; use ``bin/dev help
test`` for the wrapper's own usage.

.. _dev-generated-environment:

.. list-table:: Environment supplied to foreground commands
   :header-rows: 1
   :widths: 26 40 34

   * - Variable
     - Value
     - Supplied to
   * - ``DB_NAME``, ``PGDATABASE``
     - This worktree's database name.
     - All foreground commands and all managed processes.
   * - ``DEV_PROJECT``
     - The ``project_id``.
     - ``test``, ``jstest``, ``lint``, ``check``, ``run``, and managed processes.
   * - ``DEV_WORKTREE``
     - Absolute path of this worktree.
     - As above.
   * - ``DEV_WORKTREE_ID``
     - The worktree ID.
     - As above.
   * - ``PYTHONPATH``
     - The repository root, prepended to any existing value.
     - As above.
   * - ``DEV_BASE_HOST``
     - The Portless hostname while the environment is running with Portless; empty otherwise.
     - ``manage``, ``run``, and managed processes. Always empty for ``test``, ``jstest``,
       ``lint``, and ``check``.
   * - ``DEV_DJANGO_PORT``, ``DEV_VITE_PORT``
     - The allocated ports. ``DEV_DJANGO_PORT`` is ``0`` when Portless assigns the Django port.
     - ``run`` while the environment is running, and managed processes.
   * - ``DISABLE_SSR``
     - ``1``, so verification does not depend on a running server-side rendering server.
     - ``test``, ``lint``, and ``check``.
   * - ``VIRTUAL_ENV``, ``PATH``
     - ``verification_virtualenv`` activated: ``VIRTUAL_ENV`` set and its ``bin`` directory
       prepended to ``PATH``. Skipped when the caller already has a virtualenv active.
     - ``test``, ``lint``, and ``check``.

Values from the ``[environment]`` tables of the configuration layers are supplied to every
foreground command and managed process as well, below the invoking shell in precedence. The
generated variables cannot be overridden from those tables or from the shell.

.. _dev-command-manage:

``manage``
~~~~~~~~~~

.. program:: bin/dev manage

.. code-block:: bash

   bin/dev manage COMMAND [ARGS...]

Runs ``manage_command`` followed by the given arguments in ``django_cwd`` against this worktree's
database, and exits with the management command's exit status. All arguments are passed through
untouched. The database must already exist; ``up`` creates it. The environment does not need to be
running, but when it is running with Portless, ``DEV_BASE_HOST`` carries the worktree's hostname.

.. code-block:: bash

   bin/dev manage shell
   bin/dev manage makemigrations billing
   bin/dev manage prepare_worktree_db

.. _dev-command-verification:

``test``, ``jstest``, ``lint``, ``check``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   bin/dev test [ARGS...]
   bin/dev jstest [ARGS...]
   bin/dev lint [ARGS...]
   bin/dev check [ARGS...]

Each verb executes the argv configured by the matching setting (``test_command``,
``jstest_command``, ``lint_command``, or ``check_command``) from the repository root, appending
every supplied argument literally. Nothing is re-quoted, re-ordered, or interpreted, so native
options such as ``--keepdb`` or ``--help`` reach the underlying tool unchanged, and the exit status
is returned as is.

A verb whose setting is empty is disabled: invoking it fails with a message naming the setting to
add to ``config/dev.toml``, and ``doctor`` reports it as a warning.

``test``, ``lint``, and ``check`` are Python-backed. They set ``DISABLE_SSR=1`` and, unless the
caller already has a virtualenv active, activate ``verification_virtualenv`` by exporting
``VIRTUAL_ENV``, prepending its ``bin`` directory to ``PATH``, and removing ``PYTHONHOME``; they
fail before running anything when that virtualenv is not provisioned. ``jstest`` runs with the
caller's environment plus the generated variables and never touches a Python virtualenv. None of
these verbs receives the allocated ports, and ``DEV_BASE_HOST`` is empty for all of them, so they
do not depend on the environment being up.

.. code-block:: bash

   bin/dev test app.tests.test_billing --keepdb
   bin/dev jstest src/billing
   bin/dev lint
   bin/dev check

.. _dev-command-run:

``run``
~~~~~~~

.. program:: bin/dev run

.. code-block:: bash

   bin/dev run [--cwd PATH] -- COMMAND [ARGS...]

Replaces the runner with an arbitrary command that receives the worktree environment. While the
environment is running, that includes the allocated ports and the Portless hostname; otherwise only
the database and identity variables are set. No virtualenv is activated. Put ``--`` before the
command so that its own options are not mistaken for ``run`` options.

.. option:: --cwd PATH

   Working directory for the command, relative to the repository root; defaults to the repository
   root. It must exist and must be inside the repository.

.. code-block:: bash

   bin/dev run -- uv run pytest -x
   bin/dev run --cwd django-root -- uv run python manage.py showmigrations

Configuration commands
----------------------

Configuration is merged from three layers; see :doc:`configuration` for the layers, their
precedence, and every setting.

.. _dev-command-config-show:

``config show``
~~~~~~~~~~~~~~~

.. program:: bin/dev config show

.. code-block:: bash

   bin/dev config show [--json | --show-environment-values]

Prints the path of each layer, every effective setting with the layer that supplied it
(``default``, ``project``, ``global``, or ``worktree``), and the names of the configured
``[environment]`` variables with their source layer. Environment values are shown as
``<redacted>``.

.. option:: --show-environment-values

   Print the actual environment values. Allowed only when both stdin and stdout are a terminal,
   and cannot be combined with ``--json``.

.. option:: --json

   Print ``{"schemaVersion": 1, "settings": [...], "environment": [...]}``, where each setting has
   ``key``, ``value``, and ``source`` and each environment entry has ``key`` and ``source``.
   Environment values are never included.

.. _dev-command-config-paths:

``config paths``
~~~~~~~~~~~~~~~~

.. program:: bin/dev config paths

.. code-block:: bash

   bin/dev config paths [--json]

Prints the path of each configuration layer from lowest to highest precedence, and whether the
file exists.

.. option:: --json

   Print ``{"schemaVersion": 1, "paths": [...]}``, where each entry has ``scope`` (``project``,
   ``global``, or ``worktree``), ``path``, ``present``, and ``committed``.

.. _dev-command-config-edit:

``config edit``
~~~~~~~~~~~~~~~

.. program:: bin/dev config edit

.. code-block:: bash

   bin/dev config edit {project|global|worktree}

Opens one layer in the editor named by ``EDITOR`` (default ``vi``), creating the file first when it
does not exist. The ``global`` and ``worktree`` files and their directories are created with
private permissions.

.. option:: LAYER

   ``project`` opens the committed ``config/dev.toml``. ``global`` opens
   ``~/.config/alliance/dev/<project_id>/config.toml`` (or the equivalent under
   ``XDG_CONFIG_HOME``), which applies to every worktree of this project on this machine.
   ``worktree`` opens ``.dev-server/config.toml``, which applies to this checkout only.

Project setup commands
----------------------

.. _dev-command-install:

``install``
~~~~~~~~~~~

.. program:: bin/dev install

.. code-block:: bash

   uvx --from alliance-platform-dev alliance-dev install [PATH] [--yes] [--force] \
       [--django-cwd DIR] [--tool-source SOURCE]

Adds the runner to an existing Django project. It is the one command that works before a project
has ``config/dev.toml``, which is why it is normally run through ``uvx`` rather than ``bin/dev``.
The installer:

1. Chooses the project root: ``PATH`` when given, otherwise ``ALLIANCE_DEV_PROJECT_DIR``, otherwise
   the nearest directory at or above the current directory that contains ``pyproject.toml``.
2. Proposes a ``project_id`` slug derived from the project name in ``pyproject.toml`` and asks to
   confirm it.
3. Locates ``manage.py`` and records its directory as ``django_cwd``. ``django-root/manage.py`` is
   preferred, then the shallowest candidate; several candidates prompt for a choice. Vite is
   assumed to use the repository root.
4. Derives the verification commands. Existing executable ``bin/run-tests-django.sh``,
   ``bin/run-tests-frontend.sh``, ``bin/lint.sh``, and ``bin/check.sh`` scripts are used when
   present. Otherwise ``test`` falls back to ``manage.py test`` and ``jstest`` to a ``package.json``
   script that invokes Vitest (with ``--run`` added so that it does not watch). Anything still
   unresolved is prompted for, or left disabled with ``--yes``.
5. Writes ``bin/dev`` (executable, pinning the running package version) and ``config/dev.toml``,
   and adds ``.dev-server/`` to ``.gitignore`` unless an existing entry already ignores that
   directory.
6. When ``.husky/pre-commit`` or ``.husky/pre-push`` exist, writes
   ``bin/run-with-dev-env-if-managed`` and rewrites each hook's final command to run through it
   (see :doc:`installation`). Interactive installs ask first; ``--yes`` applies the change. Hooks
   whose final command cannot be wrapped safely are reported for manual attention.
7. Prints the Portless-related Django settings to add to the development settings module, and the
   next steps.

Interactive installation requires a terminal; pass ``--yes`` otherwise. Existing files with
identical content are left alone. Existing files whose content differs prompt for replacement
interactively, and are an error non-interactively unless ``--force`` is given. The installer does
not edit Django settings.

.. option:: PATH

   The project root. Cannot be combined with ``--project-dir``.

.. option:: --yes

   Accept discovered defaults without prompting: the suggested project ID, the best-ranked
   ``manage.py`` candidate, disabled verbs for unresolved verification commands, and the Husky hook
   update.

.. option:: --force

   Replace an existing ``bin/dev``, ``config/dev.toml``, or hook wrapper whose content differs.

.. option:: --django-cwd DIR

   The directory containing ``manage.py``, relative to the project root. Skips discovery.

.. option:: --tool-source SOURCE

   The ``uvx --from`` requirement written into ``bin/dev``. Defaults to
   ``alliance-platform-dev==<version of the running installer>``, or to the local source checkout
   when the installer itself runs from one. Use it to pin a pre-release, a Git revision, or a local
   path.

.. _dev-command-init-project:

``init-project``
~~~~~~~~~~~~~~~~

.. program:: bin/dev init-project

.. code-block:: bash

   bin/dev init-project REPOSITORY-NAME

Replaces the ``template-django`` identity in a project created from the Alliance Django template.
When ``pyproject.toml`` still names the project ``template-django``, the name becomes the slug of
``REPOSITORY-NAME``. When ``config/dev.toml`` has no ``project_id`` or still uses
``template-django``, ``project_id`` is set to the slug of the project name (the new name, or the
existing name when ``pyproject.toml`` was already renamed). Files that already carry a real
identity are left unchanged.

The command deliberately runs before the usual configuration validation, which would otherwise
reject the template ``project_id``; it only requires ``config/dev.toml`` and ``pyproject.toml`` to
exist. The same operation is available without the command-line interface as
``python -m alliance_platform.dev.init_project REPOSITORY-NAME``, run from the project root.

.. option:: REPOSITORY-NAME

   The repository name. It is lower-cased, and every run of characters other than letters and
   digits becomes a single hyphen.

Output and exit status
----------------------

* Results and progress lines go to stdout. ``Error: ...`` and ``Warning: ...`` lines go to stderr.
* Every ``--json`` output is a single JSON document carrying ``"schemaVersion": 1``; check it
  before parsing. Environment values and other secrets are never included.
* The exit status is ``0`` on success; ``1`` for an expected error (invalid configuration, a
  missing tool, an environment that is not running, a refused destructive action) after printing
  ``Error:``, or for ``doctor`` when any check is an ``error``; ``2`` for a command-line usage
  error; and ``130`` when interrupted with ``Ctrl-C``.
  During ``up`` and ``restart``, ``SIGHUP`` and ``SIGTERM`` are handled the same way so that a
  partial start is cleaned up before exiting. ``manage``, ``test``, ``jstest``, ``lint``,
  ``check``, and ``run`` return the exit status of the command they ran.
* ``status`` reports problems in its output, not through the exit status; it exits ``0`` even when
  nothing is running.

Environment variables read by the tool
--------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Variable
     - Effect
   * - ``ALLIANCE_DEV_PROJECT_DIR``
     - The project root. The ``bin/dev`` launcher sets it to the repository containing the
       launcher; ``--project-dir`` overrides it.
   * - ``ALLIANCE_DEV_INVOCATION_NAME``
     - The name the tool uses for itself in usage and error messages. The launcher sets it to
       ``bin/dev``; the default is ``alliance-dev``.
   * - ``EDITOR``
     - The editor used by ``config edit``. Defaults to ``vi``.
   * - ``ALLIANCE_DEV_OWNER_KIND``, ``ALLIANCE_DEV_OWNER_ID``, ``ALLIANCE_DEV_LEASE_EXPIRES_AT``
     - Owner metadata recorded in the registry when an environment is registered; see
       :doc:`architecture`. Interactive use is recorded as ``human`` without setting anything.
   * - ``XDG_CONFIG_HOME``, ``XDG_STATE_HOME``, ``XDG_CACHE_HOME``
     - Base directories for the global configuration layer, the registry, and the lock files
       respectively. Defaults are ``~/.config``, ``~/.local/state``, and ``~/.cache``.
   * - ``NVM_DIR``
     - Where ``up`` and ``restart`` look for ``nvm.sh`` when ``.nvmrc`` requires a Node.js version
       that is not active. Defaults to ``~/.nvm``, then the Homebrew locations.
   * - ``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASSWORD``
     - PostgreSQL connection settings for the runner's own ``psql``, ``createdb``, and ``dropdb``
       invocations, read from the shell, the ``[environment]`` tables, or the repository-root
       ``.env``; see :doc:`configuration`.

The ``bin/dev`` launcher additionally reads ``ALLIANCE_DEV_TOOL_SOURCE``,
``ALLIANCE_DEV_UV_CACHE_DIR``, ``UV_CACHE_DIR``, and ``TMPDIR`` (see :doc:`installation`), and the
generated Git hook wrapper reads ``BIN_DEV_HOOK_ENV``.
