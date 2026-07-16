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
``database_template``, ``createdevdata_args``, and ``db_prepare_command``.

When ``database_template`` is set, a missing worktree database is cloned from that PostgreSQL
database and ``createdevdata`` is skipped. Migrations still run. ``db_prepare_command`` is a list
of Django management-command arguments that runs only after a new worktree database has been
created. It receives the generated database environment and, when Portless is selected, the
worktree hostname in ``DEV_BASE_HOST``.

Project layout and commands are controlled by:

.. code-block:: toml

   django_cwd = "django-root"
   vite_cwd = "."
   manage_command = ["uv", "run", "python", "manage.py"]
   django_command = ["uv", "run", "python", "manage.py", "runserver"]
   vite_command = ["yarn", "dev"]
   test_command = ["bin/run-tests-django.sh"]
   jstest_command = ["bin/run-tests-frontend.sh"]
   lint_command = ["bin/lint.sh"]
   check_command = ["bin/check.sh"]

Every command is a non-empty argv array and never a joined shell string. Configured working
directories must stay inside the repository and exist when used. ``startup_timeout`` controls
readiness. ``extra_processes`` entries contain ``name``, ``command``, optional ``cwd``, and
optional ``required``. The ``environment`` table supplies non-secret project overrides;
application secrets remain in ``.env`` and are loaded only for control/database operations.

Launcher and generated worktree variables are reserved and cannot be set in configuration.
