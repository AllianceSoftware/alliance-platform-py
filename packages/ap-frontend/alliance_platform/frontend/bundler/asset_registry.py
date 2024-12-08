import warnings

from alliance_platform.frontend.bundler.resource_registry import FrontendResourceRegistry

warnings.warn(
    "alliance_platform.frontend.asset_registry is deprecated; use alliance_platform.frontend.resource_registry instead",
    DeprecationWarning,
    stacklevel=2,
)

FrontendAssetRegistry = FrontendResourceRegistry
