import json
import logging
from pathlib import Path
from textwrap import dedent
import time

from django.conf import settings

from alliance_platform_frontend.bundler.base import PathResolver
from alliance_platform_frontend.bundler.base import RegExAliasResolver
from alliance_platform_frontend.bundler.base import RelativePathResolver
from alliance_platform_frontend.bundler.base import ResolveContext
from alliance_platform_frontend.bundler.base import SourceDirResolver
from alliance_platform_frontend.bundler.vite import ViteBundler

logger = logging.getLogger("common_frontend")

test_dir = settings.TEST_DIRECTORY

bundler_mode = settings.VITE_BUNDLER_MODE
use_module_preload_polyfill = False
server_details_path = settings.FRONTEND_BUILD_CACHE / "vite-server-address.json"
server_state_path = settings.FRONTEND_BUILD_CACHE / "vite-server-state.json"
server_details = {}

suppress_dev_notice = False

if server_details_path.exists():
    server_details = json.loads(server_details_path.read_text())

if bundler_mode == "development" and server_details:
    # this is set by `writeServerDetails` in util.ts
    bundler_mode = server_details["serverType"]


class AlliancePlatformPackageResolver(PathResolver):
    """Resolves strings that begin with ``./`` or ``../`` as relative to ``context.source_path``"""

    node_modules_dir: Path

    def __init__(self, node_modules_dir: Path):
        super().__init__()
        self.node_modules_dir = node_modules_dir

    def resolve(self, path: str, context: ResolveContext):
        if path.startswith("@alliancesoftware/ui") or path.startswith("@alliancesoftware/icons"):
            return self.node_modules_dir / path
        return None


source_dir = test_dir / "frontend/src"
node_modules_dir = test_dir / "node_modules"


def wait_for_server():
    if server_state_path.exists():
        server_details = json.loads(server_state_path.read_text())
        if server_details.get("status") == "starting":
            logger.warning(
                "Vite server is starting... web requests will wait until this resolves before loading"
            )
            warning_logged = False
            start = time.time()
            while server_details.get("status") == "starting":
                time.sleep(0.1)
                server_details = json.loads(server_state_path.read_text())
                if not warning_logged and (time.time() - start) > 10:
                    logger.warning(
                        "Vite appears to be taking a while to build. Check your `yarn dev` or `yarn preview` command is running and has not crashed"
                    )
                    warning_logged = True


vite_bundler = ViteBundler(
    root_dir=test_dir,
    path_resolvers=[
        AlliancePlatformPackageResolver(node_modules_dir),
        RelativePathResolver(),
        RegExAliasResolver("^/", str(settings.PROJECT_DIR) + "/"),
        SourceDirResolver(source_dir),
    ],
    mode=bundler_mode,
    server_build_dir=settings.FRONTEND_PRODUCTION_DIR,
    build_dir=test_dir / "server-build",
    server_host=server_details.get("host", "localhost"),
    server_port=server_details.get("port", "5173"),
    server_protocol=server_details.get("protocol", "http"),
    production_ssr_url="http://localhost:4173",
    wait_for_server=wait_for_server,
    use_module_preload_polyfill=use_module_preload_polyfill,
)


if vite_bundler.mode == "preview" and not suppress_dev_notice:
    print(  # noqa
        dedent(
            """
        Running Vite in preview mode. This will serve production assets in dev.

        Make sure `yarn preview` is running."""
        )
    )
