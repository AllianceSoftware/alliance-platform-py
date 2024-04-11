from pathlib import Path


class FrontendAssetRegistry:
    """Stores any extra assets in addition to those found in templates that should be included in the frontend build

    This should be populated on startup such that the assets are available when
    :class:`extract_frontend_assets <alliance_platform.frontend.management.commands.extract_frontend_assets.Command>` runs.

    The registry to use is specified by the  :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.FRONTEND_ASSET_REGISTRY`
    setting

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
            if not filename.is_absolute():
                raise ValueError(
                    f'Filenames should be absolute - e.g. Try `settings.PROJECT_DIR / "{filename}"`'
                )
            if not filename.exists():
                raise ValueError(f"{filename} was added to frontend asset registry but does not exist")
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
