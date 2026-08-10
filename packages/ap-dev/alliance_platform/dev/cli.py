from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any

from . import DEV_PROTOCOL_VERSION
from . import invocation_name
from . import package_version
from .commands import CommandDelegates
from .config import ensure_private_file
from .config import load_config
from .environment import build_control_environment
from .environment import build_process_environment
from .environment import prepare_node_environment
from .errors import ConfigError
from .errors import DevError
from .identity import resolve_identity
from .init_project import update_project_identity
from .install_project import install_project
from .install_project import resolve_install_root
from .lifecycle import DevEnvironment
from .models import ConfigPaths
from .models import DevConfig
from .models import DoctorReport
from .models import EnvironmentRecord
from .models import EnvironmentRemovalResult
from .models import EnvironmentSummary
from .models import LogRecord
from .models import RestartResult
from .models import StartResult
from .models import StatusRecord
from .models import StopResult
from .models import WorktreeIdentity
from .runner import SubprocessRunner


@dataclass(frozen=True)
class Context:
    repo: Path
    config: DevConfig
    identity: WorktreeIdentity
    process_environment: dict[str, str]
    control_environment: dict[str, str]


PROJECT_MARKERS = (Path("config/dev.toml"), Path("pyproject.toml"))


def repository_root(
    project_dir: str | Path | None = None,
    *,
    environ: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    controlled = project_dir
    source = "--project-dir"
    if controlled is None and "ALLIANCE_DEV_PROJECT_DIR" in environment:
        controlled = environment["ALLIANCE_DEV_PROJECT_DIR"]
        source = "ALLIANCE_DEV_PROJECT_DIR"

    if controlled is not None:
        candidate = Path(controlled).expanduser().resolve()
        missing = [str(marker) for marker in PROJECT_MARKERS if not (candidate / marker).is_file()]
        if missing:
            raise ConfigError(
                f"Invalid project directory from {source}: {candidate}; missing {', '.join(missing)}"
            )
        return candidate

    candidate = (Path.cwd() if cwd is None else cwd).resolve()
    while True:
        if all((candidate / marker).is_file() for marker in PROJECT_MARKERS):
            return candidate
        if candidate.parent == candidate:
            expected = ", ".join(str(marker) for marker in PROJECT_MARKERS)
            raise ConfigError(
                f"Could not find an Alliance dev project from {cwd or Path.cwd()}; expected {expected}"
            )
        candidate = candidate.parent


def make_context(*, project_dir: str | None = None, node_environment: bool = False) -> Context:
    repo = repository_root(project_dir)
    config = load_config(repo)
    process_environment = build_process_environment(config)
    control_environment = build_control_environment(repo, config)
    if node_environment:
        process_environment = prepare_node_environment(repo, process_environment)
    identity = resolve_identity(repo, config)
    return Context(
        repo,
        config,
        identity,
        process_environment,
        control_environment,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=invocation_name(),
        description="Worktree-aware development environment and verification commands.",
    )
    parser.add_argument("--project-dir", metavar="PATH", help="Alliance project repository root")
    parser.add_argument(
        "--version",
        action="version",
        version=(f"alliance-platform-dev {package_version()} (development protocol {DEV_PROTOCOL_VERSION})"),
    )
    subparsers = parser.add_subparsers(dest="command")

    up = subparsers.add_parser("up", help="start Django, Vite, and configured processes")
    up.add_argument("--no-portless", action="store_true")

    down = subparsers.add_parser("down", help="stop this worktree's environment")
    down.add_argument("--drop-db", action="store_true", help="also drop this worktree's database")
    down.add_argument("--yes", action="store_true", help="confirm a destructive non-interactive action")

    restart = subparsers.add_parser("restart", help="restart the environment or one process")
    restart.add_argument("target", nargs="?", default="all")

    status = subparsers.add_parser("status", help="show this worktree or all active worktrees")
    status.add_argument("--all", action="store_true", dest="all_worktrees")
    status.add_argument("--json", action="store_true", dest="as_json")

    environment = subparsers.add_parser("env", help="list or remove registered environments")
    environment_subparsers = environment.add_subparsers(dest="env_action", required=True)
    environment_list = environment_subparsers.add_parser(
        "list",
        help="list registered environments for this project",
    )
    environment_list.add_argument("--json", action="store_true", dest="as_json")
    environment_remove = environment_subparsers.add_parser(
        "remove",
        help="remove a registered environment and its owned resources",
    )
    environment_remove.add_argument("environment_id", help="exact registered worktree ID")
    environment_remove.add_argument(
        "--yes",
        action="store_true",
        help="confirm a destructive non-interactive action",
    )

    logs = subparsers.add_parser("logs", help="show live pane output or the last saved snapshot")
    logs.add_argument("target", nargs="?")
    logs.add_argument("--lines", type=int)
    attach = subparsers.add_parser("attach", help="attach to the session or one process")
    attach.add_argument("target", nargs="?")

    url = subparsers.add_parser("url", help="print this worktree's Django URL")
    url.add_argument("--json", action="store_true", dest="as_json")

    manage = subparsers.add_parser("manage", help="run manage.py against the worktree database")
    manage.add_argument("args", nargs=argparse.REMAINDER)

    run = subparsers.add_parser("run", help="run a foreground command with the worktree environment")
    run.add_argument("--cwd", default=".", help="working directory within the repository")
    run.add_argument("args", nargs=argparse.REMAINDER)

    doctor = subparsers.add_parser("doctor", help="diagnose dependencies and Portless capability")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    for name, help_text in (
        ("test", "run Django tests"),
        ("jstest", "run Vitest once"),
        ("lint", "delegate to the repository lint command"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("args", nargs=argparse.REMAINDER)
    subparsers.add_parser("check", help="run the complete local Definition-of-Done gate")

    init_project = subparsers.add_parser("init-project", help="replace template project identity")
    init_project.add_argument("repository_name")

    install = subparsers.add_parser("install", help="add bin/dev and configuration to a Django project")
    install.add_argument("path", nargs="?", help="project directory; defaults to discovery from cwd")
    install.add_argument("--yes", action="store_true", help="accept discovered defaults non-interactively")
    install.add_argument("--force", action="store_true", help="replace existing bin/dev and config/dev.toml")
    install.add_argument("--tool-source", help="uv --from source written into bin/dev")
    install.add_argument("--django-cwd", type=Path, help="directory containing manage.py")

    config = subparsers.add_parser("config", help="inspect or edit layered configuration")
    config_subparsers = config.add_subparsers(dest="config_action", required=True)
    config_show = config_subparsers.add_parser("show", help="show effective configuration")
    config_show.add_argument("--json", action="store_true", dest="as_json")
    config_show.add_argument("--show-environment-values", action="store_true")
    config_paths = config_subparsers.add_parser("paths", help="show every config layer path")
    config_paths.add_argument("--json", action="store_true", dest="as_json")
    config_edit = config_subparsers.add_parser("edit", help="edit a config layer")
    config_edit.add_argument(
        "layer",
        choices=("project", "global", "worktree"),
    )
    return parser


def _config_layer_path(config: DevConfig, layer: str) -> Path:
    if layer == "project":
        return config.paths.project
    if layer == "global":
        return config.paths.global_
    return config.paths.worktree


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    if isinstance(value, tuple):
        value = list(value)
    return json.dumps(value, sort_keys=True)


def _effective_settings(config: DevConfig) -> dict[str, Any]:
    return {
        "project_id": config.project_id,
        "django_port_base": config.django_port_base,
        "vite_port_base": config.vite_port_base,
        "portless": config.portless,
        "database_template": config.database_template,
        "database_template_strategy": config.database_template_strategy,
        "createdevdata_args": list(config.createdevdata_args),
        "db_prepare_command": list(config.db_prepare_command),
        "django_cwd": config.django_cwd,
        "vite_cwd": config.vite_cwd,
        "verification_virtualenv": config.verification_virtualenv,
        "manage_command": list(config.manage_command),
        "test_command": list(config.test_command),
        "jstest_command": list(config.jstest_command),
        "lint_command": list(config.lint_command),
        "check_command": list(config.check_command),
        "django_command": list(config.django_command),
        "vite_command": list(config.vite_command),
        "startup_timeout": config.startup_timeout,
        "extra_processes": [
            {
                "name": process.name,
                "command": list(process.command),
                "cwd": process.cwd,
                "required": process.required,
            }
            for process in config.extra_processes
        ],
    }


def _config_path_records(config: DevConfig) -> list[dict[str, object]]:
    return [
        {
            "scope": layer,
            "path": str(_config_layer_path(config, layer)),
            "present": _config_layer_path(config, layer).exists(),
            "committed": layer == "project",
        }
        for layer in ("project", "global", "worktree")
    ]


def _show_paths(config: DevConfig, *, as_json: bool = False) -> None:
    records = _config_path_records(config)
    if as_json:
        print(json.dumps({"schemaVersion": 1, "paths": records}, indent=2, sort_keys=True))
        return
    print("Config layers (lowest → highest precedence):\n")
    for record in records:
        state = "present" if record["present"] else "—"
        print(f"  {record['scope']:<9} {record['path']}  {state}")


def _show_config(
    config: DevConfig,
    *,
    as_json: bool = False,
    show_environment_values: bool = False,
) -> None:
    if as_json and show_environment_values:
        raise ConfigError("--show-environment-values cannot be used with --json")
    if show_environment_values and not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ConfigError("--show-environment-values requires an interactive terminal")

    settings = [
        {
            "key": key,
            "value": value,
            "source": config.setting_sources[key],
        }
        for key, value in _effective_settings(config).items()
    ]
    environment = [
        {"key": key, "source": config.environment_sources[key]} for key in sorted(config.environment)
    ]
    if as_json:
        print(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "settings": settings,
                    "environment": environment,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    _show_paths(config)
    print("\nEffective settings:")
    for setting in settings:
        print(f"  {setting['key']:<22} {_format_value(setting['value']):<30} [{setting['source']}]")
    print("\nConfigured environment:")
    if not environment:
        print("  (none)")
    for item in environment:
        value = config.environment[item["key"]] if show_environment_values else "<redacted>"
        print(f"  {item['key']:<22} {_format_value(value):<30} [{item['source']}]")


def _editor(path: Path, *, private: bool = False) -> None:
    if private:
        ensure_private_file(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    command = shlex.split(os.environ.get("EDITOR", "vi"))
    if not command:
        raise DevError("EDITOR is empty")
    os.execvp(command[0], [*command, str(path)])


def _handle_config(context: Context, args: argparse.Namespace) -> int:
    action = args.config_action
    if action == "show":
        _show_config(
            context.config,
            as_json=getattr(args, "as_json", False),
            show_environment_values=getattr(args, "show_environment_values", False),
        )
    elif action == "paths":
        _show_paths(context.config, as_json=args.as_json)
    elif action == "edit":
        _editor(
            _config_layer_path(context.config, args.layer),
            private=args.layer != "project",
        )
    return 0


def _confirm_database(identity: WorktreeIdentity, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise DevError("Dropping the database requires --yes in a non-interactive terminal")
    print(f"This will permanently drop database '{identity.database_name}'.")
    try:
        response = input(f"Type {identity.database_name} to continue: ").strip()
    except EOFError:
        return False
    return response == identity.database_name


def _confirm_environment(record: EnvironmentRecord, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise DevError("Removing an environment requires --yes in a non-interactive terminal")
    database_action = "will drop if present" if record.database_owned else "will retain (not registry-owned)"
    print(f"Remove environment '{record.environment_id}'?")
    print(f"  Worktree: {record.worktree_path} ({'exists' if record.worktree_exists else 'missing'})")
    print(f"  Session:  {record.session_name} ({record.session_state})")
    print(f"  Database: {record.database_name} ({database_action})")
    try:
        response = input(f"Type {record.environment_id} to continue: ").strip()
    except EOFError:
        return False
    return response == record.environment_id


def _print_warnings(warnings: tuple[str, ...]) -> None:
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)


def _print_progress(message: str) -> None:
    print(f"→ {message}", flush=True)


def _print_environment(environment: EnvironmentSummary, portless_reason: str | None) -> None:
    print(f"Branch:    {environment.branch or '(detached HEAD)'}")
    print(f"Worktree:  {environment.worktree_id}")
    print(f"DB:        {environment.database_name}")
    print(f"Django:    {environment.django_url}")
    print(f"Vite:      {environment.vite_url}")
    if portless_reason is not None:
        print(f"Portless:  {portless_reason}")


def _print_start_result(result: StartResult) -> None:
    if result.already_running:
        print("→ dev environment already running")
        print(f"Django: {result.environment.django_url}")
        print(f"Vite:   {result.environment.vite_url}")
        return
    if result.frontend_symlink_removed:
        print("→ removed shared node_modules symlink")
    if result.frontend_dependencies_installed:
        print("→ installed frontend dependencies")
    else:
        print("→ frontend dependencies already installed")
    if result.recovered_incomplete_database:
        print("→ recovered incomplete database setup")
    _print_environment(result.environment, result.portless_reason)
    print("\nReady.")
    print(f"Django: {result.environment.django_url}")
    print(f"Logs:   {invocation_name()} logs")
    _print_warnings(result.warnings)


def _print_stop_result(result: StopResult, session_name: str) -> None:
    if result.was_running:
        print(f"→ stopped '{session_name}'")
    else:
        print("→ dev environment was not running")
    if result.recovered_incomplete_database:
        print("→ removed incomplete database setup")
    elif result.database_drop_requested:
        state = "dropped" if result.database_dropped else "did not exist"
        print(f"→ database {state}")
    print("Stopped. Logs and port assignments were preserved.")
    _print_warnings(result.warnings)


def _print_restart_result(result: RestartResult) -> None:
    _print_environment(result.environment, result.portless_reason)
    print("\nRestarted all processes.")
    print(f"Django: {result.environment.django_url}")
    _print_warnings(result.warnings)


def _status_payload(record: StatusRecord) -> dict[str, object]:
    return {
        "projectId": record.project_id,
        "worktree": {
            "id": record.worktree_id,
            "path": record.worktree,
            "branch": record.branch,
        },
        "session": {
            "name": record.session_name,
            "state": record.session_state,
        },
        "readiness": record.readiness,
        "databaseName": record.database_name,
        "urls": {
            "django": record.django_url,
            "vite": record.vite_url,
        },
        "processes": [
            {
                "name": process.name,
                "required": process.required,
                "state": process.state,
                "exitCode": process.exit_code,
                "signal": process.signal,
            }
            for process in record.processes
        ],
    }


def _print_status(
    records: tuple[StatusRecord, ...],
    *,
    all_worktrees: bool,
    as_json: bool,
) -> None:
    if as_json:
        payload: dict[str, object] = {"schemaVersion": 1}
        if all_worktrees:
            payload["environments"] = [_status_payload(record) for record in records]
        else:
            payload["environment"] = _status_payload(records[0])
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if not records:
        print("No active dev environments")
        return
    for record in records:
        print(
            f"{record.session_name}  "
            f"({record.branch or 'detached'}; {record.session_state}; {record.readiness})"
        )
        print(f"  worktree: {record.worktree}")
        print(f"  django:   {record.django_url}")
        print(f"  vite:     {record.vite_url}")
        print(f"  db:       {record.database_name}")
        failures = [process.name for process in record.processes if process.state != "running"]
        if failures:
            print(f"  failures: {', '.join(failures)}")
        print()


def _environment_payload(record: EnvironmentRecord) -> dict[str, object]:
    return {
        "id": record.environment_id,
        "state": record.state,
        "projectId": record.project_id,
        "worktree": {
            "path": record.worktree_path,
            "branch": record.worktree_branch,
            "exists": record.worktree_exists,
        },
        "session": {
            "name": record.session_name,
            "state": record.session_state,
        },
        "database": {
            "name": record.database_name,
            "present": record.database_present,
            "owned": record.database_owned,
            "setupPending": record.database_setup_pending,
        },
        "owner": {
            "kind": record.owner_kind,
            "id": record.owner_id,
            "leaseExpiresAt": record.lease_expires_at,
        },
        "activity": {
            "registeredAt": record.registered_at,
            "lastSeenAt": record.last_seen_at,
            "lastStartedAt": record.last_started_at,
            "lastStoppedAt": record.last_stopped_at,
        },
    }


def _print_environments(records: tuple[EnvironmentRecord, ...], *, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "environments": [_environment_payload(record) for record in records],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if not records:
        print("No registered dev environments")
        return
    for record in records:
        owner = record.owner_kind + (f":{record.owner_id}" if record.owner_id else "")
        database_state = (
            "present"
            if record.database_present is True
            else "absent"
            if record.database_present is False
            else "unknown"
        )
        ownership = "owned" if record.database_owned else "unowned"
        print(f"{record.environment_id}  ({record.state}; {record.worktree_branch or 'detached'})")
        print(f"  worktree: {record.worktree_path}")
        print(f"  session:  {record.session_name} ({record.session_state})")
        print(f"  db:       {record.database_name} ({database_state}; {ownership})")
        print(f"  owner:    {owner}")
        print(f"  seen:     {record.last_seen_at}")
        print()


def _print_environment_removal(result: EnvironmentRemovalResult) -> None:
    if result.session_stopped:
        print("→ session stopped")
    if result.database_dropped:
        print("→ owned database dropped")
    elif result.database_was_absent:
        print("→ owned database already absent")
    elif result.database_retained:
        print("→ database retained because it is not registry-owned")
    print(f"Removed environment {result.environment_id} from the registry.")


def _print_logs(records: tuple[LogRecord, ...], *, one_process: bool) -> None:
    for record in records:
        if one_process:
            print(record.output)
        else:
            print(f"━━━ {record.name} (last {record.lines} lines) ━━━")
            print(record.output)
            print()


def _doctor_payload(report: DoctorReport) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "tool": {
            "version": report.package_version,
            "protocolVersion": report.protocol_version,
        },
        "identity": {
            "projectId": report.project_id,
            "worktreeId": report.worktree_id,
            "worktreePath": report.worktree_path,
            "databaseName": report.database_name,
            "sessionName": report.session_name,
        },
        "configPaths": _config_path_records_from_paths(report.config_paths),
        "state": {
            "path": str(report.state.path),
            "status": report.state.status,
            "databaseSetupPending": report.state.database_setup_pending,
        },
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail} for check in report.checks
        ],
    }


def _config_path_records_from_paths(paths: ConfigPaths) -> list[dict[str, object]]:
    return [
        {
            "scope": scope,
            "path": str(getattr(paths, "global_" if scope == "global" else scope)),
            "present": getattr(paths, "global_" if scope == "global" else scope).exists(),
            "committed": scope == "project",
        }
        for scope in ("project", "global", "worktree")
    ]


def _print_doctor(report: DoctorReport, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(_doctor_payload(report), indent=2, sort_keys=True))
        return
    print(f"Project:          {report.project_id}")
    print(f"Tool version:     {report.package_version}")
    print(f"Protocol version: {report.protocol_version}")
    print(f"Branch:           {report.branch or '(detached HEAD)'}")
    print(f"Worktree ID:      {report.worktree_id}")
    print(f"Database:         {report.database_name}")
    print(f"tmux session:     {report.session_name}")
    print(f"State:            {report.state.status} ({report.state.path})")
    print("\nChecks:")
    for check in report.checks:
        print(f"  {check.status:<7} {check.name:<24} {check.detail}")


def dispatch(argv: list[str], parser: argparse.ArgumentParser | None = None) -> int:
    parser = build_parser() if parser is None else parser
    passthrough = {"manage", "test", "jstest", "lint"}
    command_index = 0
    if argv[:1] == ["--project-dir"]:
        if len(argv) < 2:
            parser.parse_args(argv)
        command_index = 2
    elif argv[:1] and argv[0].startswith("--project-dir="):
        command_index = 1
    if len(argv) > command_index and argv[command_index] in passthrough:
        # Everything after these verbs belongs to the underlying native tool,
        # including arguments such as --help that argparse would otherwise eat.
        parsed_globals = parser.parse_args([*argv[:command_index], argv[command_index]])
        parsed_globals.args = argv[command_index + 1 :]
        args = parsed_globals
    else:
        args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "attach" and not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise DevError("attach requires an interactive terminal")
    if args.command == "init-project":
        try:
            update_project_identity(repository_root(args.project_dir), args.repository_name)
        except (OSError, ValueError) as error:
            raise DevError(f"Could not initialize project identity: {error}") from error
        return 0
    if args.command == "install":
        if args.path is not None and args.project_dir is not None:
            raise DevError("Use either install PATH or --project-dir, not both")
        repo = resolve_install_root(args.path or args.project_dir)
        install_project(
            repo,
            assume_yes=args.yes,
            force=args.force,
            tool_source=args.tool_source,
            django_cwd=args.django_cwd,
        )
        return 0
    node_commands = {"up", "restart"}
    context = make_context(project_dir=args.project_dir, node_environment=args.command in node_commands)
    runner = SubprocessRunner()
    dev = DevEnvironment(
        runner,
        context.repo,
        context.config,
        context.identity,
        context.process_environment,
        context.control_environment,
    )
    commands = CommandDelegates(
        context.repo,
        context.config,
        context.identity,
        context.process_environment,
    )
    command = args.command
    if command == "up":
        _print_start_result(
            dev.start(
                no_portless=args.no_portless,
                on_progress=_print_progress,
            )
        )
    elif command == "down":
        if args.drop_db and not _confirm_database(context.identity, args.yes):
            print("Cancelled.")
            return 0
        _print_stop_result(
            dev.stop(drop_database=args.drop_db),
            context.identity.session_name,
        )
    elif command == "restart":
        if args.target == "all":
            _print_restart_result(dev.restart())
        else:
            result = dev.restart_process(args.target)
            print(f"Restarted {result.name}.")
            _print_warnings(result.warnings)
    elif command == "status":
        _print_status(
            dev.status_records(all_worktrees=args.all_worktrees),
            all_worktrees=args.all_worktrees,
            as_json=args.as_json,
        )
    elif command == "env":
        if args.env_action == "list":
            _print_environments(dev.environment_records(), as_json=args.as_json)
        elif args.env_action == "remove":
            record = dev.environment_record(args.environment_id)
            if not _confirm_environment(record, args.yes):
                print("Cancelled.")
                return 0
            _print_environment_removal(dev.remove_environment(args.environment_id))
    elif command == "logs":
        _print_logs(
            dev.log_records(args.target, lines=args.lines),
            one_process=args.target is not None,
        )
    elif command == "attach":
        dev.attach(args.target)
    elif command == "url":
        url = dev.live_environment(require_ready=True).django_url
        print(json.dumps({"url": url}) if args.as_json else url)
    elif command == "manage":
        return dev.manage(args.args)
    elif command == "run":
        run_args = list(args.args)
        if run_args[:1] == ["--"]:
            run_args.pop(0)
        if not run_args:
            raise DevError(f"Usage: {invocation_name()} run [--cwd PATH] -- <command> [args...]")
        commands.run(
            run_args,
            cwd=args.cwd,
            environment=dev.command_environment(),
        )
    elif command == "doctor":
        _print_doctor(dev.doctor_report(), as_json=args.as_json)
    elif command == "test":
        commands.test(args.args)
    elif command == "jstest":
        commands.jstest(args.args)
    elif command == "lint":
        commands.lint(args.args)
    elif command == "check":
        commands.check()
    elif command == "config":
        return _handle_config(context, args)
    else:
        parser.print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    if argv and argv[0] == "help":
        if len(argv) == 1:
            parser.print_help()
            return 0
        parser.parse_args([argv[1], "--help"])
        return 0
    if not argv:
        parser.print_help()
        return 0
    try:
        return dispatch(argv, parser)
    except KeyboardInterrupt as error:
        print("Interrupted.", file=sys.stderr)
        _print_warnings(tuple(getattr(error, "__notes__", ())))
        return 130
    except DevError as error:
        print(f"Error: {error}", file=sys.stderr)
        _print_warnings(tuple(getattr(error, "__notes__", ())))
        return 1
