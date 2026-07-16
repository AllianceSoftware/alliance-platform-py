from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from . import invocation_name
from .errors import DevError
from .models import PortlessDiagnostics
from .runner import Runner
from .runner import require_success

PORTLESS_SHELL_ADAPTER = r'''display=$1
cwd=$2
shift 2
case ${PORT-} in
  ''|*[!0-9]*) echo "$display: Portless requires a numeric PORT from 1 to 65535" >&2; exit 64 ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "$display: Portless requires a numeric PORT from 1 to 65535" >&2
  exit 64
fi
cd "$cwd" || exit 1
set -- "$@" "127.0.0.1:$PORT"
exec "$@"'''


@dataclass(frozen=True)
class PortlessSelection:
    enabled: bool
    reason: str


@dataclass(frozen=True)
class _PortlessCapability:
    cli_path: str | None
    supported: bool
    detail: str


class PortlessAdapter:
    """Keep optional Portless policy and CLI behaviour behind one boundary."""

    def __init__(
        self,
        runner: Runner,
        repo: Path,
        environment: dict[str, str],
        app_name: str,
    ) -> None:
        self.runner = runner
        self.repo = repo
        self.environment = environment
        self.app_name = app_name
        self._capability: _PortlessCapability | None = None

    def cli_path(self) -> str | None:
        return self.runner.which("portless", self.environment)

    def _detect_capability(self) -> _PortlessCapability:
        if self._capability is not None:
            return self._capability
        cli_path = self.cli_path()
        if cli_path is None:
            self._capability = _PortlessCapability(None, False, "CLI is not installed")
            return self._capability

        main_help = self.runner.run(
            ["portless", "--help"],
            cwd=self.repo,
            env=self.environment,
            capture=True,
        )
        get_help = self.runner.run(
            ["portless", "get", "--help"],
            cwd=self.repo,
            env=self.environment,
            capture=True,
        )
        main_contract = ("--name <name>", "auto-start the proxy")
        get_contract = ("portless get <name>", "--no-worktree")
        supported = (
            main_help.returncode == 0
            and get_help.returncode == 0
            and all(value in main_help.stdout for value in main_contract)
            and all(value in get_help.stdout for value in get_contract)
        )
        detail = (
            "CLI supports named launch, on-demand proxy startup, and URL construction"
            if supported
            else "CLI does not advertise the required named-launch, proxy auto-start, and URL contracts"
        )
        self._capability = _PortlessCapability(cli_path, supported, detail)
        return self._capability

    def select(self, policy: str, *, force_off: bool = False) -> PortlessSelection:
        if policy not in {"auto", "off", "required"}:
            raise DevError(f"Unknown Portless policy: {policy!r}")
        if force_off:
            return PortlessSelection(False, "disabled by --no-portless")
        if policy == "off":
            return PortlessSelection(False, "disabled by configuration")

        capability = self._detect_capability()
        if capability.cli_path is None:
            if policy == "required":
                raise DevError(
                    "Portless is required by configuration, but the 'portless' CLI is not "
                    'installed. Install Portless or set portless = "off" (or "auto") in '
                    "your dev configuration."
                )
            return PortlessSelection(False, "CLI not installed; using localhost")

        if not capability.supported:
            if policy == "required":
                raise DevError(
                    "Portless is required by configuration, but the installed CLI does not "
                    f"support the named-launch, proxy auto-start, and URL commands used by {invocation_name()}. "
                    'Upgrade Portless or set portless = "off" (or "auto") in your dev configuration.'
                )
            return PortlessSelection(False, f"{capability.detail}; using localhost")
        return PortlessSelection(True, capability.detail)

    def resolve_url(self) -> str:
        result = self.runner.run(
            ["portless", "get", self.app_name, "--no-worktree"],
            cwd=self.repo,
            env=self.environment,
            capture=True,
        )
        require_success(result, "Resolving the Portless URL")
        url = result.stdout.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise DevError(f"Portless returned an invalid URL: {url!r}")
        return url

    def django_command(self, cwd: Path, argv: tuple[str, ...]) -> list[str]:
        return [
            "portless",
            "--name",
            self.app_name,
            "--",
            "/bin/sh",
            "-c",
            PORTLESS_SHELL_ADAPTER,
            "alliance-dev-portless",
            invocation_name(),
            str(cwd),
            *argv,
        ]

    def diagnostics(self, policy: str) -> PortlessDiagnostics:
        capability = self._detect_capability() if policy != "off" else None
        cli_path = capability.cli_path if capability is not None else self.cli_path()
        if policy == "off":
            reason = "disabled by configuration"
        elif capability is not None and capability.supported:
            reason = capability.detail
        elif policy == "required":
            reason = f"startup will fail: {capability.detail if capability else 'CLI is unavailable'}"
        else:
            reason = f"{capability.detail if capability else 'CLI is unavailable'}; localhost will be used"
        return PortlessDiagnostics(
            policy=policy,
            cli=cli_path,
            proxy_availability_capability=(
                "autoStart"
                if capability is not None and capability.supported
                else ("unsupported" if cli_path else "unavailable")
            ),
            selected=bool(policy != "off" and capability is not None and capability.supported),
            reason=reason,
        )
