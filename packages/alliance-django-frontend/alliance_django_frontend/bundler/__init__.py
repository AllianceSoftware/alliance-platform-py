from django.conf import settings
from django.utils.module_loading import import_string

from common_frontend.bundler.base import BaseBundler


# Removed caching as it causes problems with tests is you don't force the cache clear (e.g. if one test
# sets FRONTEND_BUNDLER it's value will be cached for other tests - so order matters).
# Probably makes very little difference anyway - looks like `import_string` itself does some caching.
# @lru_cache
def get_bundler() -> BaseBundler:
    """Get the configured bundler

    Returns the module according to the ``settings.FRONTEND_BUNDLER`` setting
    """
    if isinstance(settings.FRONTEND_BUNDLER, BaseBundler):
        return settings.FRONTEND_BUNDLER
    return import_string(settings.FRONTEND_BUNDLER)
