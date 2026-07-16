How project isolation works
===========================

Project-owned integration
-------------------------

Each application commits two integration files:

* ``bin/dev`` pins and invokes the ``alliance-platform-dev`` release from PyPI; and
* ``config/dev.toml`` defines the project's processes, commands, ports, and database setup.

The package is not installed into the application's Python environment and does not import the
application or Django. Project-specific behavior remains in management commands, shell scripts,
and the committed configuration. This keeps upgrades explicit and lets every worktree use the
same tool release.

Worktree identity and isolation
-------------------------------

The runner combines the committed ``project_id`` with the canonical Git worktree path to derive a
stable worktree identity. That identity scopes the PostgreSQL database, tmux session, allocated
ports, state files, and Portless hostname. Renaming a branch does not change the environment's
identity.

State and recent process output live under the worktree's ``.dev-server`` directory. Machine-wide
locks coordinate port allocation and database setup when several projects or agents start at the
same time. ``bin/dev status --all`` shows the active environments belonging to the project.

Processes and commands
----------------------

``bin/dev up`` starts Django, Vite, and configured extra processes in a dedicated tmux session.
Required processes participate in readiness reporting; optional processes can run alongside them
without preventing the environment from becoming ready. ``restart``, ``logs``, and ``attach``
operate on that worktree's session.

Foreground commands such as ``manage``, ``test``, ``lint``, and ``run`` receive the same generated
database, port, and hostname environment as the servers. This prevents a command run from one
worktree from silently falling back to another worktree's database.

Application environment and secrets
-----------------------------------

The launcher preserves the developer's executable environment while keeping package installation
isolated from the application. The runner reads application ``.env`` values for PostgreSQL control
operations, while application processes remain responsible for their normal settings loading.
Application secrets are not loaded into the ``uvx`` environment that installs the runner.

Generated values such as ``DB_NAME``/``PGDATABASE``, service ports, worktree identity, and
``DEV_BASE_HOST`` take precedence where required for isolation. Keep application secrets in the
project's established secret mechanism rather than committing them to ``config/dev.toml``.

Compatibility and cleanup
-------------------------

Stopping an environment leaves its database available for the next ``up``. Use
``bin/dev down --drop-db`` for a clean reset, with ``--yes`` in non-interactive automation.
Before adopting a release with documented compatibility changes, stop active environments and
follow its changelog instructions. Invalid worktree state under ``.dev-server`` can be regenerated
after confirming that no interrupted database setup needs recovery.
