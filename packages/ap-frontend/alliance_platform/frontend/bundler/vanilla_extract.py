from functools import lru_cache
import json
from json import JSONDecodeError
import logging
from pathlib import Path
import re
import warnings

from alliance_platform.core.settings import ap_core_settings
from allianceutils.middleware import CurrentRequestMiddleware
from django.http import HttpRequest
import requests

from ..settings import ap_frontend_settings
from . import get_bundler
from .base import BaseBundler

logger = logging.getLogger("alliance_platform.frontend")


def resolve_vanilla_extract_cache_names(bundler: BaseBundler, filename: Path | str):
    cache_name = re.sub(r"[/.]", "_", str(filename))
    if bundler.is_development():
        cache_fn = ap_core_settings.CACHE_DIR / f"development-css-mappings/{cache_name}.json"
        import_script_filename = ap_core_settings.CACHE_DIR / f"development-css-mappings/{cache_name}.ts"
        return cache_fn, import_script_filename
    return ap_frontend_settings.PRODUCTION_DIR / "production-css-mappings" / f"{cache_name}.json", None


class VanillaExtractClassMapping:
    """Class that stores class mappings for a Vanilla Extract file

    The mappings are read from a JSON file written by the plugin defined in ``vanillaExtractWithExtras.ts``.

    If a class is referenced but does not exist a warning will be logged.

    In dev this triggers a request to the bundler to write the mappings if they don't exist. It also stores the import script
    filename so that it can be included in the template via ViteCssEmbed
    """

    #: Mapping of class names to their hashed names
    mapping: dict[str, str] | None
    bundler: BaseBundler
    cache_filename: Path

    _last_request: HttpRequest | None

    def __init__(self, bundler: BaseBundler, filename: Path):
        self._last_request = None
        self.filename = filename.relative_to(bundler.root_dir)
        self.bundler = bundler
        self.cache_filename, self._import_script_filename = resolve_vanilla_extract_cache_names(
            bundler, self.filename
        )
        self._create_mapping()

    @property
    def import_script_filename(self):
        """Only set in dev mode. This is a typescript file generated by ``vanillaExtractWithExtras.ts`` that imports the css and setups up HMR"""
        self._check_mapping()
        return self._import_script_filename

    def _create_mapping(self):
        bundler = self.bundler
        cache_fn = self.cache_filename
        if bundler.is_development():
            try:
                # Always trigger request otherwise we can end up with out of date mappings. It seems fast enough in practice.
                # Previously this checked if cache file exists and only triggered request if it didn't, but sometimes resulted
                # in out of date mappings.
                # This request will cause the above mappings file to be written out
                response = requests.get(
                    get_bundler().get_url(str(self.filename) + "?writeStyleMappings=1"), timeout=3
                )
                if response.status_code == 404:
                    warnings.warn(f"Requested stylesheet '{self.filename}' doesn't exist")
                elif response.status_code == 500:
                    warnings.warn(
                        f"Requested stylesheet '{self.filename}' could not be processed. Check for syntax errors and refresh."
                    )
                elif response.status_code == 200:
                    if not cache_fn.exists():
                        # In my testing this only happened if you removed the frontend cache dir after server was started.
                        warnings.warn(
                            f"Requested stylesheet '{self.filename}' exists but class name mappings could not be extracted. Try making a change to the file or restarting the dev server."
                        )
            except requests.exceptions.ConnectionError:
                warnings.warn(f"Failed to get requested stylesheet '{self.filename}'. Is 'yarn dev' running?")
            except requests.exceptions.Timeout:
                warnings.warn(f"Failed to get requested stylesheet '{self.filename}' - request timed out")
        if not cache_fn.exists():
            warnings.warn(
                f"Mapping for {self.filename} was not found in expected location '{cache_fn}'. No class names will be resolved for this tag."
            )
            self.mapping = None
        else:
            self._load_mapping()

    def _load_mapping(self):
        bundler = self.bundler
        cache_fn = self.cache_filename
        try:
            self.mapping = json.loads(cache_fn.read_text())
        except JSONDecodeError:
            if bundler.is_development():
                warnings.warn(
                    f"Failed to parse cache file {cache_fn}. This may be due to reading the file as it's being written to - try refreshing the browser."
                )
            else:
                logger.exception(f"Failed to parse cache file {cache_fn} - check file is valid JSON.")

    def _check_mapping(self):
        """If dev server has been restarted the cache dir will have been cleared.

        This detects such a case and regenerates files."""
        if self.bundler.is_development() and (
            not self.cache_filename.exists() or self.cache_filename.exists() and not self.mapping
        ):
            self._create_mapping()
        elif (
            self.bundler.is_development()
            and self.cache_filename.exists()
            and self._last_request != CurrentRequestMiddleware.get_request()
        ):
            # This handles the case where the cache file exists but may need to be reloaded. This can happen if the
            # class name mapping existed already, but details changed. For example, if you change:
            # style([class1, class2]) to style([class1]) then the key will exist in both cases, but the value will
            # change from something like '.class1 .class2' to '.class1'. Because of caching this won't be picked up otherwise.
            self._load_mapping()

        self._last_request = CurrentRequestMiddleware.get_request()

    def __getattr__(self, name):
        self._check_mapping()
        if self.mapping is None:
            warnings.warn(
                f"Requested class name '{name}' from '{self.filename}' cannot be resolved because the mapping file was not found."
            )
            return ""
        if name not in self.mapping:
            warnings.warn(
                f"Requested class name '{name}' from '{self.filename}' does not exist. Known classes are: {', '.join(self.mapping.keys())}"
            )
            return ""

        return self.mapping.get(name)

    def __str__(self):
        return f"VanillaExtractClassMapping({self.mapping})"


@lru_cache()
def resolve_vanilla_extract_class_mapping(bundler: BaseBundler, filename: Path):
    """Resolve the ``VanillaExtractClassMapping`` instance to use for the given filename"""
    return VanillaExtractClassMapping(bundler, filename)
