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

State needed to operate the current worktree and recent process output live under its
``.dev-server`` directory. The runner also maintains a machine-wide resource registry under
``$XDG_STATE_HOME/alliance/dev/registry/v1`` (normally
``~/.local/state/alliance/dev/registry/v1``). Each project has a directory keyed by
``project_id``, with one JSON record per worktree identity.

The registry records resource identity and lifecycle information—not application secrets. This
includes the original worktree path, Git identity, database ownership, tmux session, ports, last
activity, and optional agent owner/lease metadata. Writes are atomic; registry directories and
files are private to the local user. A record remains after ``down`` while its database is being
retained, and is removed after ``down --drop-db`` or successful cleanup of a failed first startup.
This means the database can still be discovered after its Git worktree directory has been removed.
Agent launchers can identify themselves with ``ALLIANCE_DEV_OWNER_KIND``,
``ALLIANCE_DEV_OWNER_ID``, and an ISO-8601 ``ALLIANCE_DEV_LEASE_EXPIRES_AT`` value; ordinary
interactive use is recorded as human-owned without requiring any configuration.

Machine-wide locks coordinate port allocation and database setup when several projects or agents
start at the same time. ``bin/dev status --all`` shows the project's currently active tmux
environments; ``bin/dev env list`` reads the registry and additionally shows stopped environments
that still own resources. ``bin/dev env remove WORKTREE-ID`` can clean up a registered environment
after its worktree has disappeared. It refuses mismatched tmux or deterministic resource identity,
and never drops a database that is not marked as registry-owned.

Processes and commands
----------------------

``bin/dev up`` starts Django, Vite, and configured extra processes in a dedicated tmux session.
Required processes participate in readiness reporting; optional processes can run alongside them
without preventing the environment from becoming ready. ``restart``, ``logs``, and ``attach``
operate on that worktree's session.

Foreground commands such as ``manage``, ``test``, ``lint``, and ``run`` receive the same generated
database, port, and hostname environment as the servers. This prevents a command run from one
worktree from silently falling back to another worktree's database.

The isolated ``uvx`` tool environment is removed before any project command runs. Python-backed
verification delegates (``test``, ``lint``, and ``check``) then preserve an explicitly active
caller virtualenv or activate the configured project ``verification_virtualenv``. Frontend-only
``jstest`` and arbitrary ``run`` commands do not receive implicit Python virtualenv behavior.

Projects using Husky can route pre-commit and pre-push commands through the generated
``bin/run-with-dev-env-if-managed`` wrapper. It selects ``bin/dev run`` only when the worktree has
managed state, retaining the normal inherited environment for checkouts that have not used the
runner.

Application environment and secrets
-----------------------------------

The launcher preserves the developer's executable environment while keeping package installation
isolated from the application. The runner reads application ``.env`` values for PostgreSQL control
operations, while application processes remain responsible for their normal settings loading.
Application secrets are not loaded into the ``uvx`` environment that installs the runner.

Generated values such as ``DB_NAME``/``PGDATABASE``, service ports, worktree identity, and
``DEV_BASE_HOST`` take precedence where required for isolation.

Compatibility and cleanup
-------------------------

Stopping an environment leaves its database available for the next ``up``. Use
``bin/dev down --drop-db`` for a clean reset, with ``--yes`` in non-interactive automation.
Prefer dropping the database before removing a worktree. If the worktree is removed first, its
machine-wide registry record retains the database name and ownership information needed by
``bin/dev env remove``.

Before adopting a release with documented compatibility changes, stop active environments and
follow its changelog instructions. Invalid worktree state under ``.dev-server`` can be regenerated
after confirming that no interrupted database setup needs recovery.
