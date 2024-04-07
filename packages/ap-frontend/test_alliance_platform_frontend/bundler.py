import logging
from pathlib import Path

from alliance_platform.frontend.bundler.base import PathResolver
from alliance_platform.frontend.bundler.base import RegExAliasResolver
from alliance_platform.frontend.bundler.base import RelativePathResolver
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.bundler.base import SourceDirResolver
from alliance_platform.frontend.bundler.vite import ViteBundler
from alliance_platform.frontend.settings import ap_frontend_settings
from django.conf import settings

logger = logging.getLogger("alliance_platform_frontend")

root_dir = settings.BASE_DIR

bundler_mode = settings.VITE_BUNDLER_MODE


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


source_dir = root_dir / "frontend/src"
node_modules_dir = root_dir / "node_modules"

vite_bundler = ViteBundler(
    root_dir=root_dir,
    path_resolvers=[
        AlliancePlatformPackageResolver(node_modules_dir),
        RelativePathResolver(),
        RegExAliasResolver("^/", str(settings.PROJECT_DIR) + "/"),
        SourceDirResolver(source_dir),
    ],
    mode=bundler_mode,
    server_build_dir=ap_frontend_settings.PRODUCTION_DIR,
    build_dir=root_dir / "server-build",
    server_host="localhost",
    server_port="5273",
    server_protocol="http",
    production_ssr_url="http://localhost:4273",
)
