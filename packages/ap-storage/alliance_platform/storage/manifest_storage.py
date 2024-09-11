from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.storage import ManifestFilesMixin
from django.contrib.staticfiles.storage import StaticFilesStorage


class ManifestStaticFilesExcludeHashedFilesStorage(ManifestFilesMixin, StaticFilesStorage):  # type: ignore[misc] # django-stubs internal conflict
    """Same as ManifestStaticFilesStorage but ignores files built by bundler that already include hashes"""

    def hashed_name(self, name, content=None, filename=None):
        # Check if file is in the output dir for frontend build and if so don't generate a hash
        # in the manifest for it. We let Vite generate hashes for the files it generates
        # but use the manifest for all other files (eg. other django static files)
        static_dirs = settings.STATICFILES_DIRS
        for item in static_dirs:
            if isinstance(item, (tuple, list)):
                stat_dir, src = item
                if str(src) == str(settings.FRONTEND_PRODUCTION_DIR) and Path(name).parts[0] == stat_dir:
                    return name
            elif name.startswith(item):
                return name

        return super().hashed_name(name, content, filename)
