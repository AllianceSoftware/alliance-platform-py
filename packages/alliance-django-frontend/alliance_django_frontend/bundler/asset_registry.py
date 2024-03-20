from pathlib import Path

from django.conf import settings


class FrontendAssetRegistry:
    """Stores any extra assets in addition to those found in templates that should be included in the frontend build

    This should be populated on startup such that the assets are available when
    :class:`extract_frontend_assets <common_frontend.management.commands.extract_frontend_assets.Command>` runs.

    In most cases only a single registry is required. :data:`~common_frontend.bundler.asset_registry.frontend_asset_registry`
    is the default used throughout the site.

    .. warning::

        In most cases you do not need this.

        This is necessary only for assets that can't be auto-discovered - for example in a dynamic template. If you try
        and use an asset that cannot be auto-discovered an error will be raised.

    Usage::

        from common_frontend.bundler.asset_registry import frontend_asset_registry

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


#: Registry to add files to be included in frontend build
frontend_asset_registry = FrontendAssetRegistry()
frontend_asset_registry.add_asset(
    settings.PROJECT_DIR / "django-root/common_frontend/bundler/vitePreload.ts",
    # Don't think we need this as should be discovered automatically
    # settings.PROJECT_DIR / "frontend/src/renderComponent.tsx",
    settings.PROJECT_DIR / "styles/normalize.css",
    # settings.PROJECT_DIR / "styles/theme.css.ts",
    settings.PROJECT_DIR / "frontend/src/re-exports.tsx",
    # needs to be explicitly included as is used by common_frontend.templatetags.form.FormInputNode
    settings.PROJECT_DIR / "frontend/src/components/RawHtmlWrapper.tsx",
    # Include all models so can be used by ViewModelProp
    *list(settings.PROJECT_DIR.glob("frontend/src/models/*.ts")),
)
