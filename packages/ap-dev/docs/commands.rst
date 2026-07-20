Commands
========

Global options
--------------

``--project-dir PATH`` selects a project explicitly and must precede the subcommand.
``--version`` and ``--help`` do not require a project. Without an explicit or launcher-provided
directory, the command walks upward until it finds both ``config/dev.toml`` and
``pyproject.toml``.

Lifecycle commands
------------------

``up`` starts Django, Vite, and configured extra processes in the versioned tmux backend.
``down`` stops the worktree; ``--drop-db --yes`` also removes its database. ``restart`` restarts
all processes or one named process. ``status``, ``logs``, ``url``, and ``doctor`` are
non-terminal inspection commands. ``attach`` replaces the current process with a tmux client
and requires an interactive terminal.

Foreground commands
-------------------

``manage`` runs configured management-command arguments against the worktree database.
``test``, ``jstest``, and ``lint`` append every supplied argument literally to their configured
argv. ``check`` accepts no passthrough arguments. ``run [--cwd PATH] -- COMMAND ...`` replaces
the current process with arbitrary argv inside the repository and supplies the managed
worktree environment. These foreground commands are terminal: a successful invocation uses
``exec`` rather than returning to the runner.

Configuration and initialization
--------------------------------

``config show`` reports effective settings and provenance while redacting environment values.
``config paths`` lists all layers. ``config edit project|global|worktree`` opens a layer in
``$EDITOR``; user-owned layers are created privately. ``init-project REPOSITORY-NAME`` narrowly
updates a template's project name and ID and intentionally runs before normal project-ID
validation.

``install [PATH]`` bootstraps an existing Django project before normal project discovery is
available. It creates ``bin/dev`` and ``config/dev.toml``, discovers the Django working directory,
and prints the Portless proxy settings to add to ``dev.py``. Vite is assumed to use
the repository root. Use ``--django-cwd`` to resolve an unusual Django layout, ``--yes`` for
non-interactive setup, and ``--force`` only when intentionally replacing existing generated
files. If Husky pre-commit or pre-push hooks exist, installation can update their project command
to use the generated worktree-aware hook wrapper.

JSON output from ``status``, ``url``, ``doctor``, ``config show``, and ``config paths`` is a
public automation contract and includes a schema version.
