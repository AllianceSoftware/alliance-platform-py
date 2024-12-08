import logging
from pathlib import Path
import warnings

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from django.conf import settings

logger = logging.getLogger("alliance_platform.frontend")


class FrontendResourceRegistry:
    """Stores any extra resources in addition to those found in templates that should be included in the frontend build

    This should be populated on startup such that the resources are available when
    :djmanage:`extract_frontend_resources` runs.

    The registry to use is specified by the  :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.FRONTEND_RESOURCE_REGISTRY`
    setting.

    These resources are only used when building the frontend in dev. In production, the underlying files do not need to exist -
    for example if your deployment process excludes the source files.

    .. warning::

        In most cases you do not need this.

        This is necessary only for resources that can't be auto-discovered - for example in a dynamic template. If you try
        and use a resource that cannot be auto-discovered an error will be raised.

    Usage::

        frontend_resource_registry = FrontendResourceRegistry()

        frontend_resource_registry.add_resource(
            // Adding a path will be converted to a resource for you based on the extension
            settings.PROJECT_DIR / "frontend/src/file1.tsx",
            // Pass resource directly to have full control
            ESModuleResource(settings.PROJECT_DIR / "frontend/src/file2.tsx", "MyComponent", True),
        )

    """

    _resources: set[FrontendResource]

    def __init__(self):
        self._resources = set()
        self._locked = False

    def add_asset(self, *filenames: Path):
        warnings.warn(
            "`add_asset` is deprecated; call `add_resource` instead", DeprecationWarning, stacklevel=2
        )
        return self.add_resource(*[FrontendResource.from_path(fn) for fn in filenames])

    def add_resource(self, *resources: FrontendResource | Path):
        """Add resource to be included in frontend build"""
        if self._locked:
            raise ValueError(
                "Cannot add resources to registry after it's locked. Make sure all resources are added at startup."
            )
        for resource in resources:
            if isinstance(resource, Path):
                resource = FrontendResource.from_path(resource)
            if not isinstance(resource, FrontendResource):
                raise ValueError(f"Expected FrontendResource but got {type(resource).__name__}")
            self._resources.add(resource)

    def get_resources_for_bundling(self) -> set[FrontendResource]:
        """Get all resources to include in build"""
        return set(self._resources)

    def get_unknown(self, *resources: FrontendResource) -> list[FrontendResource]:
        """From the specified resource(s) return any that aren't in the registry"""
        missing = []
        for resource in resources:
            if resource not in self._resources:
                missing.append(resource)
        return missing

    def lock(self):
        self._locked = True
        if settings.DEBUG:
            for resource in self._resources:
                if not resource.path.is_absolute():
                    logging.warning(
                        f"Resources passed to `FrontendResourceRegistry.add_resource` should have absolute paths, received {resource.path}"
                    )
                if not resource.path.exists():
                    logging.warning(
                        f"{resource.path} was added to frontend resource registry but does not exist"
                    )
