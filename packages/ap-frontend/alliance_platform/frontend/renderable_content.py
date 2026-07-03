"""Backend-neutral representation of trusted renderable HTML fragments.

Values like Django form ``help_text`` are developer-authored fragments that may contain HTML.
Rather than committing them to a specific rendering backend up front (e.g. React
``ComponentNode``), :class:`RenderableContent` stores the parsed structure so each backend can
decide how to render it:

- The React ``{% component %}`` backend converts it to nested React elements
  (see :meth:`~alliance_platform.frontend.templatetags.react.ComponentNode.resolve_prop`).
- Static HTML renderers (``{% ui %}`` in ``alliance_platform.ui``) render it directly to HTML.

``RenderableContent`` is not a sanitizer — it represents *trusted* content — but backends are
expected to refuse to render event handler attributes statically.

Attributes are stored with their HTML names (``class``, ``for``); backend-specific conversions
(e.g. React's ``className``/``htmlFor``) happen at render time.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any
from typing import Mapping
from typing import TypeGuard
from typing import Union

from django.template import Node
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE

if TYPE_CHECKING:
    from .html_parser import StrOrPromise

RenderablePart = Union["RenderableText", "RenderableElement", "RenderableTemplateNode"]


@dataclass(frozen=True)
class RenderableText:
    """Plain text content. Backends are responsible for escaping when rendering."""

    value: str


@dataclass(frozen=True)
class RenderableTemplateNode:
    """A Django template node embedded in parsed HTML via placeholder replacements.

    See the ``replacements`` argument to
    :func:`~alliance_platform.frontend.html_parser.convert_html_to_renderable_content`.
    """

    node: Node


@dataclass(frozen=True)
class RenderableElement:
    """An HTML element with attributes and child content.

    ``attrs`` uses HTML attribute names. Values are strings, ``True`` for boolean attributes, or
    template ``Node``/``NodeList`` values when the source HTML contained template placeholders;
    backends resolve those at render time.
    """

    tag: str
    attrs: Mapping[str, Any]
    children: "RenderableContent"
    #: Attribute fragments that could not be parsed statically (template node placeholders in
    #: attribute position). Backends resolve these against the render context.
    attribute_template_nodes: tuple[Node | str, ...] = ()


@dataclass(frozen=True)
class RenderableContent:
    """A sequence of renderable parts parsed from a trusted HTML fragment.

    Rendering must be explicit per backend — deliberately does not implement ``__str__``/
    ``__html__`` so call sites cannot accidentally bypass backend escaping rules.
    """

    parts: tuple[RenderablePart, ...]
    #: The original source the content was parsed from. Used for warnings and for resolving
    #: attribute template nodes.
    source_html: str = field(default="", compare=False)

    @classmethod
    def from_text(cls, value: Any) -> "RenderableContent":
        """Create content holding a single plain-text part (no HTML parsing)."""
        text = "" if value is None else str(value)
        if not text:
            return cls(())
        return cls((RenderableText(text),), source_html=text)

    @classmethod
    def from_html(cls, html: "StrOrPromise", origin: Origin | None = None) -> "RenderableContent":
        """Parse a trusted HTML fragment into renderable content.

        Invalid HTML is ignored by the parser, so the result may be empty
        (check :meth:`is_empty`) even for non-empty input.
        """
        from .html_parser import convert_html_to_renderable_content

        return convert_html_to_renderable_content(html, origin or Origin(UNKNOWN_SOURCE))

    def is_empty(self) -> bool:
        return not self.parts

    def as_plain_text(self) -> str | None:
        """Return the plain text value when the content contains only text parts.

        Returns ``None`` when the content is empty or contains elements/template nodes. Useful for
        producers that want to keep plain-text values as ordinary strings and only pass
        ``RenderableContent`` through for genuinely rich content.
        """
        texts: list[str] = []
        for part in self.parts:
            if not isinstance(part, RenderableText):
                return None
            texts.append(part.value)
        if not texts:
            return None
        return "".join(texts)


def is_renderable_content(value: Any) -> TypeGuard[RenderableContent]:
    return isinstance(value, RenderableContent)
