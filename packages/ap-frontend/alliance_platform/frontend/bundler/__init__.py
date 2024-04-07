from .base import BaseBundler


# Removed caching as it causes problems with tests is you don't force the cache clear (e.g. if one test
# sets FRONTEND_BUNDLER it's value will be cached for other tests - so order matters).
# Probably makes very little difference anyway - looks like `import_string` itself does some caching.
# @lru_cache
def get_bundler() -> BaseBundler:
    from ..settings import ap_frontend_settings

    """Get the configured bundler from settings"""
    return ap_frontend_settings.BUNDLER
