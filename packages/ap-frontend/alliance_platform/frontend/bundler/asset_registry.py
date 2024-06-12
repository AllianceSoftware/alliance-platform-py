import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("alliance_platform.frontend")


class FrontendAssetRegistry:
    """Stores any extra assets in addition to those found in templates that should be included in the frontend build

    This should be populated on startup such that the assets are available when
    :class:`extract_frontend_assets <alliance_platform.frontend.management.commands.extract_frontend_assets.Command>` runs.

    The registry to use is specified by the  :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.FRONTEND_ASSET_REGISTRY`
    setting.

    These assets are only used when building the frontend in dev. In production, the underlying assets do not need to exist -
    for example if your deployment process excludes the source files.

    .. warning::

        In most cases you do not need this.

        This is necessary only for assets that can't be auto-discovered - for example in a dynamic template. If you try
        and use an asset that cannot be auto-discovered an error will be raised.

    Usage::

        frontend_asset_registry = FrontendAssetRegistry()

        frontend_asset_registry.add_asset(
            settings.PROJECT_DIR / "frontend/src/file1.tsx",
            settings.PROJECT_DIR / "frontend/src/file2.tsx",
        )

    """

    _assets: set[Path]

    def __init__(self):
        self._assets = set()
        self._locked = False

    def add_asset(self, *filenames: Path):
        """Add asset to be included in frontend build

        Should be a path to file to include
        """
        if self._locked:
            raise ValueError(
                "Cannot add assets to registry after it's locked. Make sure all assets are added at startup."
            )
        for filename in filenames:
            self._assets.add(filename)

    def get_asset_paths(self) -> set[Path]:
        """Get all assets to include in build"""
        return set(self._assets)

    def get_unknown(self, *filenames: Path) -> list[Path]:
        """From the specified filename(s) return any that aren't in the registry"""
        missing = []
        for filename in filenames:
            if filename not in self._assets:
                missing.append(filename)
        return missing

    def lock(self):
        self._locked = True
        if settings.DEBUG:
            for filename in self._assets:
                if not filename.is_absolute():
                    logging.warning(
                        f'Filenames passed to `FrontendAssetRegistry.add` should be absolute - e.g. Try `settings.PROJECT_DIR / "{filename}"`'
                    )
                if not filename.exists():
                    logging.warning(f"{filename} was added to frontend asset registry but does not exist")
