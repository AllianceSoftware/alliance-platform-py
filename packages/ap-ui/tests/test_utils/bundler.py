from pathlib import Path
import subprocess

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.resource_registry import FrontendResourceRegistry
from alliance_platform.frontend.bundler.vite import ViteBundler
from alliance_platform.frontend.settings import ap_frontend_settings
from django.conf import settings

fixtures_dir = Path(__file__).parent.parent / "fixtures"

bundler_kwargs = dict(
    root_dir=settings.PROJECT_DIR,
    path_resolvers=[],
    build_dir=fixtures_dir / "build_test",
    server_build_dir=fixtures_dir / "server_build_test",
    server_host="localhost",
    server_port="5273",
    server_protocol="http",
    server_resolve_package_url="redirect-package-url",
)


class TestViteBundler(ViteBundler):
    def validate_path(
        self,
        filename: str | Path,
        suffix_whitelist: list[str] | None = None,
        suffix_hint: str | None = None,
        resolve_extensions: list[str] | None = None,
    ) -> Path:
        return Path(filename)

    def format_code(self, code: str):
        return code


class TestFrontendResourceRegistryByPass(FrontendResourceRegistry):
    """Bypasses unknown checks by never returning any unknown paths"""

    def get_unknown(self, *resources: FrontendResource):
        return []


bypass_frontend_resource_registry = TestFrontendResourceRegistryByPass()


def run_prettier(code):
    p = subprocess.run(
        [
            str(ap_frontend_settings.NODE_MODULES_DIR / ".bin/prettier"),
            "--stdin-filepath",
            "test.tsx",
        ],
        input=code,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise ValueError(f"Failed to format code: {p.stderr}")
    return p.stdout
