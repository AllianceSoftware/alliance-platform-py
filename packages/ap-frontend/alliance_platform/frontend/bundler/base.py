from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from django import template
from django.utils.safestring import SafeString


@dataclass
class ResolveContext:
    """Passed to :meth:`~alliance_platform.frontend.bundler.base.PathResolver.resolve` to project context for resolving paths"""

    #: The root dir for the project. Paths should sit under this.
    root_dir: Path
    #: The source path for the 'thing' path is being resolved for (e.g. a template file). May not be available.
    source_path: str | Path | None = None


class PathResolver:
    """A class that resolves a path string to a :class:`~pathlib.Path`

    This can be used to do things like resolve paths relative to a root directory, use path aliases etc.
    """

    def resolve(self, path: str, context: ResolveContext) -> Path | None:
        """Resolve a string ``path`` to a :class:`~pathlib.Path`.

        Should return ``None`` if this class was unable to resolve the path, in which case resolving will
        move onto the next resolver in order.
        """
        raise NotImplementedError


@dataclass
class RegExAliasResolver(PathResolver):
    """Resolves a path by replacing a substring using a regex"""

    #: The regular expression to match
    find: str
    #: The string to replace the match with
    replace: str

    def resolve(self, path: str, context: ResolveContext) -> Path | None:
        replaced_path = re.sub(self.find, self.replace, path)
        if replaced_path == path:
            return None
        return Path(replaced_path)


@dataclass
class SourceDirResolver(PathResolver):
    """Resolves any non-absolute path relative to ``base_dir``"""

    #: The directory to resolve paths relative to
    base_dir: Path

    def resolve(self, path: str, context: ResolveContext):
        if Path(path).is_absolute():
            return None
        return self.base_dir / path


class RelativePathResolver(PathResolver):
    """Resolves strings that begin with ``./`` or ``../`` as relative to ``context.source_path``"""

    def resolve(self, path: str, context: ResolveContext):
        if (path.startswith("./") or path.startswith("../")) and context.source_path:
            source = Path(context.source_path)
            if source.is_file():
                source = source.parent
            return (source / path).resolve()
        return None


@dataclass
class DevServerCheck:
    """Describes status of dev server"""

    #: True if dev server is running at the expected location (depends on the bundler)
    is_running: bool
    #: Read timeout
    read_timeout: bool = False
    #: The project dir the frontend dev server is running at. This is used to determine if it's for the same project as Django.
    project_dir: Path | None = None

    def is_wrong_server(self) -> bool:
        """Returns ``True`` if server is running, but it's for a different project"""
        from alliance_platform.frontend.bundler import get_bundler

        return self.is_running and get_bundler().root_dir != self.project_dir

    def is_ok(self) -> bool:
        """Returns ``True`` if server is good to use for this project"""
        return self.is_running and not self.is_wrong_server()


class BaseBundler:
    #: The root path everything sits under; all other paths are resolved relative to this
    root_dir: Path
    #: A list of :class:`~alliance_platform.frontend.bundler.base.PathResolver` instances used to resolve paths
    path_resolvers: list[PathResolver]

    def __init__(self, root_dir: Path, path_resolvers: list[PathResolver]):
        self.root_dir = root_dir
        self.path_resolvers = path_resolvers

    def is_ssr_enabled(self) -> bool:
        """Should return true if server side rendering is enabled and supported by this bundler"""
        return False

    def is_development(self) -> bool:
        """Should return true if running in development mode"""
        raise NotImplementedError

    def get_url(self, path: Path | str):
        """Return the URL to load the specified asset at ``path``"""
        raise NotImplementedError

    def get_preamble_html(self) -> str:
        """Return preamble that is included in the HTML head

        Defaults to nothing. This can be used for things like setting up hot module reloading.

        Is used by the :meth:`~alliance_platform.frontend.templatetags.bundler.bundler_preamble` tag.
        """
        return ""

    def get_embed_items(
        self, paths: Path | Iterable[Path], content_type: str | re.Pattern | None = None
    ) -> list[AssetFileEmbed]:
        """
        Generate the necessary ``AssetFileEmbed`` instances for the specified asset(s) ``paths``.

        For example, a javascript file for a component could return an AssetFileEmbed instance for its javascript content
        plus one for it's CSS content.

        Args:
            paths: The path(s) to the files to embed. If you need to embed multiple assets it's best to do them all together
                so that any necessary de-duplication can occur.
            content_type: If set only assets of that type will be embedded, otherwise all asset will be. The two common content types
                are text/css and text/javascript, but other's like image/png are also possible.
        Returns:
            The list of ``AssetFileEmbed`` instances that will be embedded.
        """
        raise NotImplementedError()

    def resolve_path(
        self,
        path: str | Path,
        context: ResolveContext,
        suffix_whitelist: list[str] | None = None,
        suffix_hint: str | None = None,
        resolve_extensions: list[str] | None = None,
    ) -> Path:
        """Resolve a string to a :class:`~pathlib.Path` based on specified ``path_resolvers``

        This allows things like relative paths or resolving relative to a custom directory.

        Each resolver in :data:`~alliance_platform.frontend.bundler.base.BaseBundler.path_resolvers` is called
        in turn until one returns a :class:`~pathlib.Path` at which point it stops.

        Args:
            path: The path to resolve
            context: The context
            suffix_whitelist: (optional) Whitelist of suffixes to accept. Each suffix should include the leading '.'. If not specified
                    then all suffixes are supported.
            suffix_hint: (optional) Hint to display as part of error message if suffix not valid
            resolve_extensions: (optional) List of extensions to try if the path as specified doesn't exist.

        Returns:
            The resolved absolute :class:`~pathlib.Path`
        """
        resolved_path = None
        if isinstance(path, Path):
            path = str(path)
        if isinstance(path, SafeString):
            # force SafeString to string so things like ``Path`` work with it
            path = "" + path
        for resolver in self.path_resolvers:
            resolved_path = resolver.resolve(path, context)
            if resolved_path:
                break
        resolved_path = Path(resolved_path or path)
        if not resolved_path.is_absolute():
            resolved_path = self.root_dir / resolved_path
        return self.validate_path(
            resolved_path,
            suffix_whitelist=suffix_whitelist,
            suffix_hint=suffix_hint,
            resolve_extensions=resolve_extensions,
        )

    def validate_path(
        self,
        filename: str | Path,
        suffix_whitelist: list[str] | None = None,
        suffix_hint: str | None = None,
        resolve_extensions: list[str] | None = None,
    ) -> Path:
        """Validate a path exists, and optional has a suffix in the whitelist

        If ``resolve_extensions`` are specified the path will be checked with each extension in turn until
        one matches. If filename doesn't exist an error is raised.

        If ``suffix_whitelist`` is specified and the filename doesn't have a suffix in the whitelist an error is raised.

        Args:
            suffix_whitelist: (optional) Whitelist of suffixes to accept. Each suffix should include the leading '.'. If not specified
                    then all suffixes are supported.
            suffix_hint: (optional) Hint to display as part of error message if suffix not valid
            resolve_extensions: (optional) List of extensions to try if the path as specified doesn't exist.
        Returns:
            The resolved absolute :class:`~pathlib.Path` with any missing extensions added.
        """
        if not isinstance(filename, Path):
            filename = Path(filename)
        if not filename.is_absolute():
            filename = self.root_dir / filename
        if not filename.exists():
            attempted = []
            if resolve_extensions and not filename.suffixes:
                for ext in resolve_extensions:
                    p = filename.parent / (filename.name + ext)
                    if self.does_asset_exist(p):
                        filename = p
                        break
                    attempted.append(str(p.relative_to(self.root_dir)))
            if not self.does_asset_exist(filename):
                message = f"'{filename}' does not exist."
                if attempted:
                    message += f" Tried the following paths: {', '.join(attempted)}"
                if not filename.suffixes and not resolve_extensions:
                    message += " You must include the file extension unless referring to a directory with an index file."
                raise template.TemplateSyntaxError(message)

        if suffix_whitelist and "".join(filename.suffixes) not in suffix_whitelist:
            message = f"file must have one of the extension(s): {', '.join(suffix_whitelist)}. Received: '{filename}'."
            if suffix_hint:
                message = f"{message} {suffix_hint}"
            raise template.TemplateSyntaxError(message)
        return filename

    def does_asset_exist(self, filename: Path):
        """Check if asset exists. By default, looks to filesystem.

        Implementations may not rely on the filesystem, e.g. once a project is built and deployed
        the source may not exist and instead the built files are stored. In Vite, this would be checked
        by seeing if the asset exists in the manifest.
        """
        return filename.exists()

    def resolve_ssr_import_path(self, path: Path | str) -> Path | str:
        """
        Resolve a path for use in an ES import when server side rendering

        This is necessary as in dev importing from the file directly will work
        (e.g. ``import { Button } from 'components/Button'``) but in production
        it needs to be the built file (e.g. ``import { Button } from '/assets/Button-abc123.js'``).

        Note that this only applies for code that will be embedded directly in script tags - code
        that is bundled by the bundler will resolve this imports itself.
        Args:
            path: The path to transform into a value that can be used in an ES import

        Returns:
            A string that can be used in an ES import
        """
        raise NotImplementedError

    def get_ssr_url(self):
        """Return the URL to use to perform server side rendering

        :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` will ``POST`` to this URL
        in development to generate the HTML for any queued SSR items.

        Note that production SSR generation works with built files and so the bundler itself isn't responsible for
        handling requests, but it may provide a URL that we use (e.g. in PREVIEW mode with Vite).

        See :ref:`ssr` for details on how SSR works.
        """
        raise NotImplementedError

    def get_ssr_headers(self) -> dict[str, str]:
        """Return any headers to add to the SSR request"""
        return {}

    def check_dev_server(self) -> DevServerCheck:
        """Check if the dev server is running.

        Should return ``DevServerCheck`` which should indicate whether the server is running
        and if so, what the project dir for that server is. This allows detection of when
        a server is running, but it's for a different project.
        """
        raise NotImplementedError

    def format_code(self, code: str):
        """Form code for output. Typically, this would only occur in development for performance reasons.

        This exists on the bundler so that we can leverage existing dev server to avoid having to shell out to a prettier
        process each time.
        """
        return code


@dataclass
class HtmlGenerationTarget:
    """The generation target for HTML produced by templates rendered in :class:`~alliance_platform.frontend.bundler.context.BundlerAssetContext`

    This is intended to be used in conjunction with things like :class:`~alliance_platform.frontend.bundler.ssr.BundlerAssetServerSideRenderer`
    where the generated HTML may differ depending on how it will be used. For example while the browser may load
    CSS externally and run all scripts, using something like WeasyPrint to generate PDFs may not need to execute
    scripts at all and prefer to load CSS inline from <style> tags.
    """

    #: Label for the target for debugging purposes (e.g. "browser")
    label: str
    #: Whether this target should include scripts in the output
    include_scripts: bool
    #: Whether this target should output CSS inline in ``<style>`` tags.
    inline_css: bool


#: The default; for use with browser where scripts will be executed and CSS included from external files.
html_target_browser = HtmlGenerationTarget("browser", include_scripts=True, inline_css=False)
#: For PDFs; scripts will not be included (only used for SSR), CSS inlined in <style> tags
html_target_pdf = HtmlGenerationTarget("pdf", include_scripts=False, inline_css=True)


class AssetFileEmbed:
    """Represents a file that should be embedded in the HTML

    Each ``AssetFileEmbed`` is responsible for generating the HTML to embed the file. This can contain logic
    for doing things differently in dev vs production, or for different targets (e.g. browser vs PDF).

    These are created by the bundler when :meth:`~alliance_platform.frontend.bundler.base.BaseBundler.get_embed_items` is called.

    If extra HTML attributes are required for the tag, they can be set on the ``html_attrs`` dict.
    """

    #: Any HTML attributes to include in the tag
    html_attrs: dict[str, str]

    def __init__(self, html_attrs: dict[str, str] | None = None):
        self.html_attrs = html_attrs or {}

    def get_content_type(self) -> str:
        """Return the content type of the file to embed

        The most common types are text/css and text/javascript. Images will be image/<type>, e.g. image/png
        """
        raise NotImplementedError

    def get_dependencies(self) -> list[AssetFileEmbed]:
        """Return any additional dependencies for this file. For example a JS file may have some CSS associated with it."""
        return []

    def generate_code(self, html_target: HtmlGenerationTarget):
        """Generate the HTML code necessary to embed this file"""
        raise NotImplementedError

    def can_embed_head(self):
        """Should return ``True`` if this file can be embedded in HTML head rather than inline where used

        This is useful to load CSS before HTML renders to avoid un-styled content, and for javascript
        to start loading before it's used for performance

        Things that display inline cannot do this (e.g. images)
        """
        return True

    def matches_content_type(self, content_type: str | re.Pattern | None):
        """Return ``True`` if this file matches the given content type

        If ``content_type`` is ``None`` then it matches anything.
        """

        # if no content_type specified then we match anything
        if content_type is None:
            return True
        if isinstance(content_type, re.Pattern):
            return content_type.match(self.get_content_type())
        return self.get_content_type() == content_type
