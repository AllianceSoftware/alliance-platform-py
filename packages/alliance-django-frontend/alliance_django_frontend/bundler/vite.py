from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from json import JSONDecodeError
import logging
import mimetypes
from pathlib import Path
import re
from typing import Callable
from typing import cast
from typing import Iterable
from urllib.parse import urljoin
import warnings

from django.conf import settings
from django.templatetags.static import static
import requests

from .base import AssetFileEmbed
from .base import BaseBundler
from .base import DevServerCheck
from .base import HtmlGenerationTarget
from .base import PathResolver
from .vanilla_extract import resolve_vanilla_extract_class_mapping

logger = logging.getLogger("alliance_django_frontend")


def _create_html_tag(tag_name: str, attrs: dict[str, str]):
    """Helper to create an HTML tag"""
    is_void_element = tag_name in ["link", "img"]
    attrs_html = " ".join([f'{key}="{value}"' for key, value in attrs.items()])
    tag = f"<{tag_name} {attrs_html}".strip()
    if is_void_element:
        return f"{tag}>"
    return f"{tag}></{tag_name}>"


def get_content_type(src: str | Path | None) -> str | None:
    if not src:
        # If no source assume js, e.g. a common chunk
        return "text/javascript"
    ext = "".join(Path(src).suffixes).lstrip(".").lower()
    if ext in ["js", "jsx", "mjs", "ts", "tsx"]:
        return "text/javascript"
    if ext in ["css", "css.ts"]:
        return "text/css"
    return mimetypes.guess_type(src)[0]


class ViteManifestAssetMissingError(Exception):
    def __init__(self, manifest_file: Path, path: Path):
        super().__init__(
            f"{path} not found in manifest file '{manifest_file.relative_to(settings.PROJECT_DIR)}'"
        )


class AssetDependencies:
    #: Any dependencies not loaded dynamically. This includes any dependencies of dependencies.
    dependencies: list[ViteManifestAsset]
    #: Any dependencies loaded dynamically (i.e. by a ``import("asset")`` call). Includes any non-dynamic dependencies
    #: of the dependencies so that all requires assets can be preloaded if desired.
    dynamic_dependencies: list[ViteManifestAsset]

    def __init__(self, dependencies: list[ViteManifestAsset], dynamic_dependencies: list[ViteManifestAsset]):
        self.dependencies = dependencies
        self.dynamic_dependencies = dynamic_dependencies

    def get_js_dependencies(self) -> list[str]:
        """Returns list of javascript file names used"""
        deps = []
        for asset in self.dependencies:
            if asset.file not in deps:
                deps.append(asset.file)
        return deps

    def get_css_dependencies(self) -> list[str]:
        """Returns list of css file names used"""
        deps = []
        for asset in self.dependencies:
            for css_file in asset.css:
                if css_file not in deps:
                    deps.append(css_file)
        return deps

    def get_dynamic_js_dependencies(self) -> list[str]:
        """Returns list of javascript file names used by any dynamic imports"""
        deps = []
        for asset in self.dynamic_dependencies:
            if asset.file not in deps:
                deps.append(asset.file)
        return deps

    def get_dynamic_css_dependencies(self) -> list[str]:
        """Returns list of css file names used by any dynamic imports"""
        deps = []
        for asset in self.dynamic_dependencies:
            for css_file in asset.css:
                if css_file not in deps:
                    deps.append(css_file)
        return deps

    def merge(self, deps: AssetDependencies):
        """Merge two ``AssetDependencies`` together"""
        for dep in deps.dependencies:
            if dep not in self.dependencies:
                self.dependencies.append(dep)
        for dep in deps.dynamic_dependencies:
            if dep not in self.dynamic_dependencies:
                self.dynamic_dependencies.append(dep)


# Cache of collected dependencies. Done here instead of on class as the dataclass is frozen
collected_dependencies_cache: dict[ViteManifestAsset, AssetDependencies] = {}


@dataclass(frozen=True)
class ViteManifestAsset:
    """
    See https://github.com/vitejs/vite/blob/main/packages/vite/src/node/plugins/manifest.ts for what this looks like
    """

    #: The manifest this asset is referenced from
    manifest: ViteManifest
    #: The built file (e.g. a js or css file)
    file: str
    #: Whether this is an entry point. If ``False`` then the file hasn't been imported directly but is a dependency of another entry point.
    is_entry: bool
    #: Whether this is used as a dynamic entry point (i.e. imported using ``import()``
    is_dynamic_entry: bool
    #: The source file this was built from. For common chunks this won't be set.
    src: str | None
    #: Any CSS file dependencies
    css: tuple[str]
    #: Can exist in the manifest file but currently not used by this
    assets: tuple[str]
    #: Any other assets this asset imports
    imports: tuple[str]
    #: Any other assets this asset imports dynamically (i.e. using ``import()``
    dynamic_imports: tuple[str]

    def collect_dependencies(self) -> AssetDependencies:
        """
        Collect all dependencies for this asset, including itself.

        This is useful to resolve all the files that are needed for a particular asset.

        See ``AssetDependencies`` for more details
        """
        # This is done to avoid circular dependencies going into infinite recursion
        if self in collected_dependencies_cache:
            return collected_dependencies_cache[self]
        dependencies: list[ViteManifestAsset] = []
        dynamic_dependencies: list[ViteManifestAsset] = []
        # this asset is included in direct dependencies
        dependencies.append(self)
        asset_dependencies = AssetDependencies(dependencies, dynamic_dependencies)
        collected_dependencies_cache[self] = asset_dependencies
        for imp in self.imports:
            asset = self.manifest.get_asset(imp)
            if asset not in dependencies:
                dependencies.append(asset)
            asset_deps = asset.collect_dependencies()
            for _asset in asset_deps.dependencies:
                if _asset not in dependencies:
                    dependencies.append(_asset)
            for _asset in asset_deps.dynamic_dependencies:
                if _asset not in dynamic_dependencies:
                    dynamic_dependencies.append(_asset)
        for imp in self.dynamic_imports:
            asset = self.manifest.get_asset(imp)
            if asset not in dynamic_dependencies:
                dynamic_dependencies.append(asset)
            # Because `imp` is a dynamic import already all dependencies of it become dynamic
            asset_deps = asset.collect_dependencies()
            for _asset in asset_deps.dependencies + asset_deps.dynamic_dependencies:
                if _asset not in dynamic_dependencies:
                    dynamic_dependencies.append(_asset)
        for dep in dependencies:
            if dep in dynamic_dependencies:
                dynamic_dependencies.remove(dep)
        return asset_dependencies

    def get_content_type(self):
        """Get the content type for this asset

        For css & vanilla extract files this will be text/css, for typescript/js it will be
        text/javascript. For other files it will be guessed from the file extension (e.g.
        image/svg+xml for svg files or image/png for .png files).
        """
        return get_content_type(self.src)


class ViteManifest:
    """Contains entries from a Vite manifest file

    Vite generates a manifest.json file as part of build based on the ``build.manifest`` and ``build.ssrManifest``
    options. This files contains a mapping from each built file to the corresponding outputs (e.g. the built javascript
    file and css files).
    """

    #: The entries from the file indexed by the source path
    entries: dict[Path, ViteManifestAsset]
    #: The file path entries were read from
    manifest_file: Path

    def __init__(self, manifest_file: Path):
        """

        Args:
            manifest_file: The path to the manifest file. This will be read as JSON and used to populate ``entries``
        """
        self.manifest_file = manifest_file
        if not manifest_file.exists():
            # We don't throw as this could happen when doing a build if `manifest.json` doesn't exist
            # yet, e.g. when calling `extract_frontend_assets`.
            warnings.warn(f"Manifest '{manifest_file} does not exist. Have you run `yarn build`?")
            return
        entries = {}
        for key, value in json.loads(manifest_file.read_text()).items():
            key = Path(key)
            entries[key] = ViteManifestAsset(
                manifest=self,
                file=value["file"],
                is_entry=value.get("isEntry", False),
                is_dynamic_entry=value.get("isDynamicEntry", False),
                # Note that this isn't necessarily the same as ``key`` although I think it is whenever it is set. For
                # common chunks that are extracted this won't be set (e.g. ``jsx-runtime-9393f670.js``).
                src=value.get("src", None),
                css=cast(tuple[str], tuple(value.get("css", []))),
                assets=cast(tuple[str], tuple(value.get("assets", []))),
                imports=cast(tuple[str], tuple(value.get("imports", []))),
                dynamic_imports=cast(tuple[str], tuple(value.get("dynamicImports", []))),
            )
            # for index files add a mapping for the directory as well, e.g. both of these:
            #  components/table/index.tsx
            #  components/table
            # will resolve to the same thing
            # This simplifies the implementation as in dev components/table will resolve but in the manifest it
            # will resolve to components/table/index.tsx
            if key.stem == "index":
                entries[key.parent] = entries[key]
        self.entries = entries
        for entry in self.entries.values():
            entry.collect_dependencies()

    def get_asset(self, path: Path | str):
        """Given ``path`` return the matching ``ViteManifestAsset`` or raise ``ViteManifestAssetMissingError`` if none found"""
        if not isinstance(path, Path):
            path = Path(path)
        if path.is_absolute():
            path = path.relative_to(settings.PROJECT_DIR)
        if path not in self.entries:
            raise ViteManifestAssetMissingError(self.manifest_file, path)
        return self.entries[path]


class ViteBundler(BaseBundler):
    #: Directory server side rendering (SSR) files are compiled to
    server_build_dir: Path
    #: Directory client side files are compiled to
    build_dir: Path
    #: Manifest for SSR (only available when in production mode)
    server_build_manifest: ViteManifest
    #: Manifest for client build (only available when in production mode)
    build_manifest: ViteManifest
    #: The mode bundler is running in; either 'development', 'production' or 'preview'
    mode: str
    #: URL for SSR (only used in production mode)
    production_ssr_url: str | None
    #: Function that can be passed that will be called before requesting assets for server.
    wait_for_server: Callable[[], None] | None = None
    #: Whether to use the Vite polyfill provided for modulepreload
    use_module_preload_polyfill: bool = False
    #: Path to the vite metdata JSON file that we use in dev to resolve optimised deps
    vite_metadata_path: Path

    def __init__(
        self,
        *,
        root_dir: Path,
        path_resolvers: list[PathResolver],
        server_build_dir: Path,
        build_dir: Path,
        server_host: str,
        server_port: str,
        server_protocol: str,
        mode: str,
        production_ssr_url: str | None = None,
        wait_for_server: Callable[[], None] | None = None,
        use_module_preload_polyfill: bool = False,
    ):
        """Bundler implementation for `Vite <https://vitejs.dev/>`_.

        Args:
            root_dir: The root path everything sits under; all other paths are resolved relative to this
            path_resolvers: A list of :class:`~alliance_django_frontend.bundler.base.PathResolver` instances used to resolve paths
            server_build_dir: The directory SSR files are outputted to (see ``yarn build:ssr``)
            build_dir: The directory client side files are outputted to (see ``yarn build:client``)
            server_host: The hostname used for the dev server (e.g. ``127.0.0.1``)
            server_port: The port used for the dev server (e.g. ``5173``)
            server_protocol: The protocol used for the dev server (``http`` or ``https``)
            mode: The mode the bundler is running in; one of ``development``, ``production`` or ``preview``
        """
        self.wait_for_server = wait_for_server
        valid_modes = ["development", "production", "preview"]
        if mode not in valid_modes:
            raise ValueError(f"'mode' must be one of {', '.join(valid_modes)}, received: '{mode}'")
        super().__init__(root_dir, path_resolvers)
        self.mode = mode
        self.use_module_preload_polyfill = use_module_preload_polyfill
        self.server_build_dir = server_build_dir
        self.build_dir = build_dir
        self.node_modules_dir = root_dir / "node_modules"
        if self.mode == "development":
            self.vite_metadata_path = self.node_modules_dir / ".vite/deps/_metadata.json"
        else:
            self.server_build_manifest = ViteManifest(server_build_dir / "manifest.json")
            self.build_manifest = ViteManifest(build_dir / "manifest.json")
        self.dev_server_url_base = ""
        self.dev_server_url = ""
        self.production_ssr_url = production_ssr_url
        if mode == "development":
            static_url = settings.STATIC_URL
            if not static_url.endswith("/"):
                static_url += "/"
            # TODO: KB29
            if static_url.startswith("http"):
                raise ValueError(f"static_url cannot be a full URL in {mode}")
            static_url = static_url.lstrip("/")
            # this is the base url for the dev server - use ``dev_server_url`` if referencing to assets
            self.dev_server_url_base = f"{server_protocol}://{server_host}:{server_port}"
            # this is what should be used anywhere assets need to be referred to
            self.dev_server_url = urljoin(self.dev_server_url_base, static_url)
        elif mode == "preview":
            self.preview_url = f"{server_protocol}://{server_host}:{server_port}"

    def resolve_url(self, path: Path | str):
        """Resolve a URL to use to serve the specified ``path``

        In development this will be served from the dev server and in production from ``STATIC_URL``
        """
        if self.wait_for_server:
            self.wait_for_server()

        if not isinstance(path, Path):
            path = Path(path)
        if self.mode in ["production", "preview"]:
            return static(str(path))
        if path.is_absolute():
            path = path.relative_to(settings.PROJECT_DIR)
        return urljoin(self.dev_server_url, str(path))

    _vite_dev_metadata: dict | None = None
    _vite_dev_last_modified: float | None = None

    def get_vite_dev_metadata(self) -> dict | None:
        if (
            self.vite_metadata_path.exists()
            and (last_modified := self.vite_metadata_path.stat().st_mtime) != self._vite_dev_last_modified
        ):
            self._vite_dev_last_modified = last_modified
            _vite_dev_metadata = json.loads(self.vite_metadata_path.read_text())
            if not isinstance(_vite_dev_metadata, dict) or "optimized" not in _vite_dev_metadata:
                warnings.warn("Invalid vite metadata file")
            else:
                self._vite_dev_metadata = _vite_dev_metadata
        return self._vite_dev_metadata

    def get_url(self, path: Path | str):
        """Get the URL to load asset as ``path``

        In development this uses the dev server, in production is served from static files.
        """
        if self.mode == "development":
            # In dev, check the vite metadata to see if the file is in the optimized list - if so
            # load from the specified file. This resolved the need to explicitly include a bunch
            # of dependencies in vite.config.ts under optimizeDeps.include
            if str(path).startswith(str(self.node_modules_dir)):
                filename = str(path).replace(str(self.node_modules_dir) + "/", "")
                metadata = self.get_vite_dev_metadata()
                if metadata and (entry := metadata["optimized"].get(filename)):
                    return self.resolve_url(
                        # Appending the hash seems to be what would happen if we used a default vite
                        # setup where it transforms the .html... but this sometimes results in a 504
                        # error and also seems to make no difference that I could determine. I also
                        # don't really understand how it's used so could be missing the point. Leaving
                        # it here for now in case it's needed in future.
                        f"node_modules/.vite/deps/{entry['file']}"  # "?v={metadata['browserHash']}"
                    )
            return self.resolve_url(path)
        # production & preview both need to use the file from the manifest
        return self.resolve_url(self.build_manifest.get_asset(path).file)

    def does_asset_exist(self, filename: Path):
        """In production node_modules might not exist - instead check the manifest file"""
        if self.mode == "development":
            return super().does_asset_exist(filename)
        try:
            self.build_manifest.get_asset(filename)
            return True
        except ViteManifestAssetMissingError:
            return False

    def get_embed_items(
        self, paths: Path | Iterable[Path] | str, content_type: str | re.Pattern | None = None
    ):
        """
        Generate the necessary ``AssetFileEmbed`` instances for the specified asset(s) ``paths``.

        For example, a javascript file for a component could return an AssetFileEmbed instance for it's javascript content,
        and one for it's CSS content.

        Note that in development passing a '.css' file in ``paths`` will embed as a javascript file as that's how Vite
        works with HMR. See ``ViteEmbedCss`` for where this is handled.

        Note that if specific items require extra attributes on the tag (e.g. ``alt="my alt tag"``) then this can be
        attached to ``item.html_attrs``.

        TODO: Doing preload need to do testing in browser to work out best approach. In particular script modules - does
        rel="preload" work or do you have to use rel="modulepreload" (which has poor support)?

        Args:
            paths: The path(s) to the asset to embed. If you need to embed multiple assets it's best to do them all together
                so that any necessary de-duplication can occur.
            content_type: If set only assets of that type will be embedded, otherwise all asset will be. The two common content types
                are text/css and text/javascript, but other's like image/png are also possible.
        Returns:
            The list of ``AssetFileEmbed`` instances that will be embedded.
        """
        if isinstance(paths, str):
            paths = Path(paths)
        paths = [paths] if isinstance(paths, Path) else paths
        # don't use a set as we want to preserve ordering
        embed_items = []
        for path in paths:
            item = self._create_embed_item(path)
            if item not in embed_items and item.matches_content_type(content_type):
                embed_items.append(item)
            for dep_item in item.get_dependencies():
                if dep_item not in embed_items and dep_item.matches_content_type(content_type):
                    embed_items.append(dep_item)
        return embed_items

    def get_preamble_html(self):
        """In development returns HMR client setup for Vite

        Optionally include vitePreload.ts in dev & production which includes polyfill for modulepreload:
        https://v2.vitejs.dev/config/#build-polyfillmodulepreload
        Not included by default as the polyfill is no longer required for modern browsers - the documentation
        appears to be out of date in recommending this (see https://caniuse.com/?search=modulepreload), but it
        may still be required if you wish to support older browsers.

        NOTE: Does not include react-refresh, use ``{% react_refresh_preamble %}`` for that.
        """
        current_dir = Path(__file__).parent.relative_to(settings.PROJECT_DIR)
        preload_tag = ""
        if self.use_module_preload_polyfill:
            preload_tag += _create_html_tag(
                "script", {"type": "module", "src": self.get_url(current_dir / "vitePreload.ts")}
            )
        if self.mode == "development":
            preload_tag += _create_html_tag(
                "script", {"type": "module", "src": urljoin(self.dev_server_url, "@vite/client")}
            )
        return preload_tag

    def is_development(self):
        return self.mode == "development"

    @lru_cache()
    def resolve_ssr_import_path(self, path: Path | str) -> Path | str:
        """See :meth:`~alliance_django_frontend.bundler.base.BaseBundler.resolve_ssr_import_path`"""
        if self.is_development():
            return path
        return self.server_build_dir / self.server_build_manifest.get_asset(path).file

    def get_development_ssr_url(self):
        """Returns the URL for SSR rendering used in dev

        See ``dev-server.ts`` for where this is handled.
        """
        return urljoin(self.dev_server_url_base, "ssr")

    def get_ssr_url(self):
        """Returns the URL for SSR rendering

        For development see ``dev-server.ts`` for where this is handled.

        For production see ``production-ssr-server.ts``
        """
        if self.is_development():
            return urljoin(self.dev_server_url_base, "ssr")
        if self.mode == "preview":
            return urljoin(self.preview_url, "ssr")
        if self.production_ssr_url:
            return urljoin(self.production_ssr_url, "ssr")
        return None

    def get_ssr_headers(self):
        """In development add an X-SSR-ROOT-DIR header to the request to the dev server.

        This lets the dev server check the request came from the same project to avoid trying to SSR requests from
        a different project which results in confusing errors.
        """
        if self.is_development():
            return {"X-SSR-ROOT-DIR": str(self.root_dir)}
        return {}

    def check_dev_server(self):
        try:
            r = requests.get(urljoin(self.dev_server_url_base, "check"), timeout=1)
            if r.status_code != 200:
                return DevServerCheck(is_running=False)
            return DevServerCheck(is_running=True, project_dir=Path(r.json()["projectDir"]))
        except requests.ConnectionError:
            return DevServerCheck(is_running=False)

    def format_code(self, code: str):
        """In dev format code using /format-code endpoint defined in dev-server.ts

        In production this is a no-op for performance reasons.
        """
        if self.is_development():
            if self.wait_for_server:
                self.wait_for_server()
            payload = {"code": code}
            try:
                response = requests.post(
                    urljoin(self.dev_server_url_base, "format-code"),
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=1,
                )
                if response.status_code != 200:
                    logger.error(
                        f"Bad response {response.status_code} from dev-server.ts for format-code action: {response.content.decode()}"
                    )
                else:
                    try:
                        return response.json()["code"]
                    except JSONDecodeError:
                        logger.error(
                            f"Failed to decode JSON from code formatting, content received: {response.content.decode()}"
                        )
            except TypeError:
                logger.exception(f"Failed to encode JSON for code formatting. Payload was: {payload}")
            except requests.exceptions.Timeout:
                logger.error("Timed out connecting to vite server for code formatting")
            except requests.exceptions.ConnectionError:
                logger.error("Failed to connect to vite server for code formatting - is it running?")
            return code
        return code

    def _create_embed_item(self, path: Path) -> AssetFileEmbed:
        content_type = get_content_type(path)
        if not content_type:
            # If not specified assume it's javascript (e.g. `core-ui` would be `core-ui/index.tsx`)
            content_type = "text/javascript"
        args = [self, path, content_type]
        for ct, cls in class_by_content_type.items():
            if isinstance(ct, re.Pattern) and content_type:
                if ct.match(content_type):
                    return cls(*args)
            elif ct == content_type:
                return cls(*args)
        # Assume default is jS
        warnings.warn(f"Unknown content type {content_type} for {path}, assuming javascript")
        return ViteJavaScriptEmbed(self, path, content_type)


class ViteEmbed(AssetFileEmbed):
    """A embed item for Vite assets"""

    #: The bundler instance to use to resolve asset paths
    bundler: ViteBundler
    #: The path to the file to embed. This will be used to resolve the final URL to embed (e.g. bundled files in production, dev server URLs in dev)
    path: Path

    def __init__(
        self, bundler: ViteBundler, path: Path, content_type: str, html_attrs: dict[str, str] | None = None
    ):
        self.bundler = bundler
        self.path = path
        self.content_type = content_type
        super().__init__(html_attrs)

    def get_content_type(self) -> str:
        return self.content_type

    def __eq__(self, other):
        return self.path == other.path and self.bundler == other.bundler and type(self) is type(other)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.path})"


class ViteJavaScriptEmbed(ViteEmbed):
    """A JavaScript embed

    In development this loads from the dev server, in production it loads from the bundled file.
    """

    def get_dependencies(self) -> list[AssetFileEmbed]:
        if self.bundler.is_development():
            return []
        asset = self.bundler.build_manifest.get_asset(self.path)
        deps = asset.collect_dependencies()
        return [
            ViteCssEmbed(self.bundler, css_path, "text/css", is_resolved_from_manifest=True)
            for css_path in deps.get_css_dependencies()
        ]

    def generate_code(self, html_target: HtmlGenerationTarget):
        if not html_target.include_scripts:
            return ""
        if self.bundler.is_development():
            return _create_html_tag("script", {"src": self.bundler.resolve_url(self.path), "type": "module"})
        asset = self.bundler.build_manifest.get_asset(self.path)
        return _create_html_tag(
            "script", {**self.html_attrs, "src": self.bundler.resolve_url(asset.file), "type": "module"}
        )


class ViteCssEmbed(ViteEmbed):
    """A CSS embed

    In development this loads from the dev server, in production it loads from the bundled file.
    """

    #: If true, then ``path`` is the path to the CSS file in the manifest. If false, then ``path`` needs to be resolved from the manifest still.
    is_resolved_from_manifest: bool

    def __init__(self, *args, is_resolved_from_manifest: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_resolved_from_manifest = is_resolved_from_manifest

    def __eq__(self, other):
        return (
            self.path == other.path
            and self.bundler == other.bundler
            and type(self) is type(other)
            and self.is_resolved_from_manifest == other.is_resolved_from_manifest
        )

    def is_vanilla_extract_file(self):
        return self.path.name.lower().endswith(".css.ts")

    def get_dependencies(self) -> list[AssetFileEmbed]:
        # In dev we load CSS via JS, so that's handled in ``generate_code`` below. But in production the main
        # ``file`` in the manifest is a useful JS file for Vanilla Extract. So instead we return the
        # actual CSS files here (I assume it will always be a single file in practice but ``asset.css`` is a list).
        # For regular CSS files ``asset.css`` will be empty and ``asset.file`` will be the CSS file itself.
        if self.bundler.is_development():
            return []
        # In production return the CSS files specified in the manifest
        asset = self.bundler.build_manifest.get_asset(self.path)
        return [
            ViteCssEmbed(self.bundler, css_file, "text/css", is_resolved_from_manifest=True)
            for css_file in asset.css
        ]

    def generate_code(self, html_target: HtmlGenerationTarget):
        # In dev, we load CSS via JS as that's how Vite works (and makes it so hot reloading works)
        if self.bundler.is_development():
            if html_target.inline_css:
                # TODO: https://kanban.alliancesoftware.com.au/board/75/card/133649/
                warnings.warn(
                    "Inlining CSS is not currently supported in dev mode. CSS will be loaded via JS instead."
                )
            if self.is_vanilla_extract_file():
                mapping = resolve_vanilla_extract_class_mapping(self.bundler, self.path)
                # In dev we load the styles via an intermediate TS file that imports the CSS file and setups
                # up hot module reloading. Without this intermediate any changes to CSS will cause a full page
                # reload rather than using HMR. See `vanillaExtractWithExtras.ts` for where this script is
                # created.
                fn = mapping.import_script_filename
                if fn is None:
                    warnings.warn(
                        f"Expected import_script_filename to be set for path {self.path}. Hot loading will not work for this file."
                    )
                else:
                    return _create_html_tag(
                        "script",
                        {
                            **self.html_attrs,
                            "src": self.bundler.resolve_url(fn),
                            "type": "module",
                            # This will block rendering until file loaded, which reduces flash of unstyled content a bit
                            # You will still get it for any components that loads it's own styles however.
                            "blocking": "render",
                        },
                    )
            return _create_html_tag(
                "script",
                {
                    **self.html_attrs,
                    "src": self.bundler.resolve_url(self.path),
                    "type": "module",
                },
            )
        if not self.is_resolved_from_manifest and self.is_vanilla_extract_file():
            # This is because the manifest contains a javascript file that does nothing when dealing with Vanilla Extract.
            # We don't want to load that, so we just ignore it. The actual CSS file is returned in ``get_dependencies``
            # above. This is a little complicated but necessary to load things correctly while handling dev where the JS
            # file is loaded, as well as handling both Vanilla Extract and regular CSS.
            # See https://kanban.alliancesoftware.com.au/board/75/card/133462/summary/
            return ""
        file = (
            self.path
            if self.is_resolved_from_manifest
            else self.bundler.build_manifest.get_asset(self.path).file
        )
        if html_target.inline_css:
            file = self.bundler.build_manifest.manifest_file.parent / file
            return f"<style>{file.read_text()}</style>"
        return _create_html_tag(
            "link",
            {**self.html_attrs, "rel": "stylesheet", "href": self.bundler.resolve_url(file)},
        )


class ViteImageEmbed(ViteEmbed):
    """An image embed

    This embeds as a ``img`` tag. In development this loads the image from the dev server, in production it loads from
    the bundled file. This is useful for cache busting (the bundled file just gets a hash in its name) or for using
    an image pipeline (see https://kanban.alliancesoftware.com.au/board/75/card/133647/ for possibility of this)
    """

    def can_embed_head(self):
        return False

    def generate_code(self, html_target: HtmlGenerationTarget):
        file = self.path
        if not self.bundler.is_development():
            asset = self.bundler.build_manifest.get_asset(self.path)
            if not len(asset.assets) == 1:
                warnings.warn(f"Expected 1 asset for image {self.path}, got {asset.assets}")
            if asset.assets:
                file = asset.assets[0]
        return _create_html_tag("img", {**self.html_attrs, "src": self.bundler.resolve_url(file)})


class_by_content_type = {
    "text/css": ViteCssEmbed,
    "text/javascript": ViteJavaScriptEmbed,
    re.compile(r"image/*"): ViteImageEmbed,
}
