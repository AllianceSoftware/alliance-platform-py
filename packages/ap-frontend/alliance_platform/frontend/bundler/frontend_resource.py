from __future__ import annotations

from dataclasses import dataclass
import mimetypes
from pathlib import Path


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


@dataclass(frozen=True)
class FrontendResource:
    """Represents a resource to be bundled by the bundler

    Previously, we just tracked files that a bundler needed to care about but this limits what you can do. For example,
    you have to bundle everything at that path, even if you use one export in the case with ES Modules. By storing the
    specifics about the resource, the bundler can then optimise this and - in the case of ES Modules - only bundle the
    resources actually used (e.g. perform tree shaking). It also means we can more easily detect what resource we
    are dealing with without relying on only inferring it from the filename.
    """

    #: The path to the resource
    path: Path

    @property
    def content_type(self) -> str:
        """Get the content type string for this resource"""
        return get_content_type(self.path)

    @classmethod
    def from_path(cls, path: Path | str):
        """Given a path, return the most appropriate resource for it"""
        if isinstance(path, str):
            path = Path(path)
        content_type = get_content_type(path)
        if content_type == "text/css":
            if path.suffixes == [".css", ".ts"]:
                from alliance_platform.frontend.templatetags.vanilla_extract import VanillaExtractResource

                return VanillaExtractResource(path)
            return CssResource(path)
        if content_type == "text/javascript":
            return JavascriptResource(path)
        if content_type and content_type.startswith("image/"):
            return ImageResource(path)
            # assume js as default
        return JavascriptResource(path)

    def serialize(self):
        """Serialize the resource for use by the bundler.

        Returns a dict with, at minimum, the following:

        - ``type`` - a string identifying the resource type. Currently, this will be one of "javascript", "css", "esmodule", "image".
        - ``path`` - path to the file for the resource

        Then any additional specific to the resource (e.g. the import details for esmodule usage)

        This is used by :djmanage:`extract_frontend_resources` to export the resource for use in the bundler.
        """
        raise NotImplementedError()


class JavascriptResource(FrontendResource):
    """A plain javascript resource.

    See also :class:`~alliance_platform.frontend.bundler.resource.ESModuleResource`"""

    @property
    def content_type(self) -> str:
        return "text/javascript"

    def serialize(self):
        return {
            "type": "javascript",
            "path": str(self.path),
        }


@dataclass(frozen=True)
class ESModuleResource(JavascriptResource):
    """An ESModule resource

    This allows the bundler to perform tree shaking rather than bundling the whole file and its dependencies.
    """

    import_name: str
    is_default_import: bool

    def serialize(self):
        return {
            "type": "esmodule",
            "path": str(self.path),
            "importName": self.import_name,
            "isDefaultImport": self.is_default_import,
        }


class CssResource(FrontendResource):
    """A CSS resource"""

    @property
    def content_type(self) -> str:
        return "text/css"

    def serialize(self):
        return {
            "type": "css",
            "path": str(self.path),
        }


class VanillaExtractResource(CssResource):
    """A Vanilla Extract CSS resource

    This will be a file with extension .css.ts
    """

    pass


class ImageResource(FrontendResource):
    """An image resource"""

    def serialize(self):
        return {
            "type": "image",
            "path": str(self.path),
        }
