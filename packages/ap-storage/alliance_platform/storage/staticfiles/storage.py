import fnmatch

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.core.exceptions import ImproperlyConfigured


class ExcludingManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """
    Custom static files storage that excludes specified files from being processed by
    :class:`~django:django.contrib.staticfiles.storage.ManifestStaticFilesStorage` (i.e., they won't have their names hashed).
    This is useful for files that are already hashed, or are never cached by the browser.

    To use this class, set it in the :setting:`STORAGES <django:STORAGES>` setting. Pass
    the ``exclude_patterns`` option as shown below. This can be set to patterns accepted
    by :external:py:func:`~fnmatch.fnmatch`

    .. note::

        The patterns accepted are not the same as regular expressions - see :external:py:mod:`fnmatch` for details.

    Usage::

        STORAGES = {
            "staticfiles": {
                "BACKEND": "alliance_platform.storage.staticfiles.storage.ExcludingManifestStaticFilesStorage",
                "OPTIONS": {"exclude_patterns": ["frontend/build/*", "*.pdf"]},
            }
        }
    """

    def __init__(self, *args, exclude_patterns=None, **kwargs):
        if exclude_patterns is None:
            raise ImproperlyConfigured(
                "ExcludingManifestStaticFilesStorage requires 'exclude_patterns' option to be set. This can be passed under the STORAGES['staticfiles']['OPTIONS']['exclude_patterns'] setting."
            )
        super().__init__(*args, **kwargs)
        self._exclude_patterns = exclude_patterns or []

    def should_exclude(self, name):
        """
        Check if the file name matches any of the exclude patterns.
        """
        for pattern in self._exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    def hashed_name(self, name, content=None, filename=None):
        """
        Override the hashed_name method to skip hashing for excluded files.
        """
        if self.should_exclude(name):
            # Return the original name without hashing
            return name
        return super().hashed_name(name, content, filename)

    def post_process(self, paths, **options):
        """
        Don't post process excluded files at all. Note that we still need ``hashed_name``
        above for any excluded files that are referenced in non-excluded files.
        """
        paths_to_hash = {}
        other_paths = []
        for path in paths:
            if self.should_exclude(path):
                other_paths.append(path)
            else:
                paths_to_hash[path] = paths[path]
        yield from super().post_process(paths_to_hash, **options)
        # add an identity mapping for excluded items otherwise base class will throw
        # an error when ``manifest_strict`` is ``True``.
        for path in other_paths:
            self.hashed_files[path] = path
