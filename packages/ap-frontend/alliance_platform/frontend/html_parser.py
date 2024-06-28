from dataclasses import dataclass
from dataclasses import field
from html.parser import HTMLParser
import re
from typing import TYPE_CHECKING
from typing import Any
from typing import Union
import warnings

from alliance_platform.frontend.util import transform_attribute_names
from django.template import Context
from django.template import Node
from django.template import NodeList
from django.template import Origin

if TYPE_CHECKING:
    from alliance_platform.frontend.templatetags.react import ComponentNode

# These are used to replace template Nodes in a string with placeholders. The resulting string can them be parsed as HTML,
# and then the placeholders replaced with the original template nodes.
_html_replacement_placeholder_prefix = "_______placeholder_____$"
_html_replacement_placeholder_suffix = "$_"
html_replacement_placeholder_template = (
    _html_replacement_placeholder_prefix + "{0}" + _html_replacement_placeholder_suffix
)


@dataclass
class Element:
    name: str
    attrs: dict


@dataclass
class HTMLElement:
    tag: str
    attributes: dict[str, str] = field(default_factory=dict)
    children: list[Union["HTMLElement", str]] = field(default_factory=list)


# Extracted from https://developer.mozilla.org/en-US/docs/Glossary/Void_element
void_elements = [
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
]

# Extracted from https://html.spec.whatwg.org/multipage/indices.html#attributes-3
boolean_html_attributes = [
    "allowfullscreen",
    "async",
    "autofocus",
    "autoplay",
    "checked",
    "controls",
    "default",
    "defer",
    "disabled",
    "formnovalidate",
    "inert",
    "ismap",
    "itemscope",
    "multiple",
    "muted",
    "nomodule",
    "novalidate",
    "open",
    "playsinline",
    "readonly",
    "required",
    "reversed",
    "selected",
    "shadowrootdelegatesfocus",
    "shadowrootclonable",
    "shadowrootserializable",
]


class HtmlTreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        # The root of the parsed tree. The tag is nonsense, but not used - it's just to make implementation easier. We
        # just use it for ``children``
        self.root = HTMLElement("Root")
        # Stack to maintain hierarchy of elements
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        element = HTMLElement(tag, {attr[0]: attr[1] for attr in attrs})
        if self.stack:
            self.stack[-1].children.append(element)
        else:
            self.root = element
        self.stack.append(element)
        # for void elements close them immediately
        if tag in void_elements:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_data(self, data):
        if data and self.stack:
            self.stack[-1].children.append(data)


def is_valid_html_attribute_name(attr_name):
    # This isn't strictly accurate, but it's good enough for our purposes.
    # https://html.spec.whatwg.org/multipage/syntax.html#attributes-2
    pattern = r'^[^\s\/<>=\'"=]+$'
    return bool(re.match(pattern, attr_name))


class HtmlAttributeTemplateNodeList:
    """A list of HTML attributes that may contain template nodes.

    Take an HTML string like::

    .. code-block:: html+django

            <input {% if value %}{{ value }}{% endif %} {% include "attrs.html" }>

    When this is parsed by ``convert_html_string`` the attributes cannot be resolved until the context is available.
    This gives us some template nodes, in the above example an ``IfNode`` and ``IncludeNode``. At some point we
    want to resolve this attributes using the context. This class is used to store this and resolve it later.
    """

    def __init__(self, attrs: list[Node | str], original_html: str, origin: Origin):
        self.original_html = original_html
        self.attrs = attrs
        self.origin = origin

    def resolve(self, context: Context) -> dict[str, str]:
        attr_str = " ".join([prop.render(context) if isinstance(prop, Node) else prop for prop in self.attrs])
        parser = HtmlTreeParser()
        parser.feed(f"<div {attr_str}></div>")
        tags = parser.root.children
        if tags:
            return transform_html_attributes(tags[0].attributes, self.original_html, self.origin)
        return {}


def convert_html_string(
    html: str, origin: Origin, *, replacements: dict[str, Node] | None = None
) -> list[Union["ComponentNode", str]]:
    """
    Given a string that may contain HTML, convert it to a tree of ``ComponentNode``s

    Note that invalid HTML is ignored, so it's possible an empty list will be returned even with a non-empty input.

    Args:
        html: The html string to convert
        origin: The template origin
        replacements: Any replacements to make in the HTML after conversion. The way this works is that a template NodeList
            is processed into a string, with any template nodes replaced with placeholders. The string is converted to
            a component tree, then any placeholders are replaced with the original template nodes.
    Returns:

    """
    # NOTE: I tried lxml initially (with & without BeautifulSoup), and it was slower for our specific use case.
    # In general, it's considered very fast, but we don't need most of its features and this simple parser was
    # faster.
    parser = HtmlTreeParser()
    # Parse the HTML
    parser.feed(html)

    tags = parser.root.children

    def handle_placeholders(content: str):
        if not replacements:
            return [content]
        parts = content.split(_html_replacement_placeholder_prefix)
        first = parts.pop(0)
        if not parts:
            return [first]
        children: list[str | Node] = []
        if first:
            children.append(first)
        for part in parts:
            placeholder_id, extra = part.split(_html_replacement_placeholder_suffix)
            children.append(replacements[placeholder_id])
            if extra:
                children.append(extra)
        return children

    def convert_attributes(attrs: dict[str, str | Any]):
        html_attribute_template_nodes = []
        transformed = {}
        for key, value in attrs.items():
            if not value:
                html_attribute_template_nodes += handle_placeholders(key)
            else:
                parts = handle_placeholders(value)
                transformed[key] = parts[0] if len(parts) == 1 else NodeList(parts)
        return transform_html_attributes(transformed, html, origin), html_attribute_template_nodes

    def convert_tree(tree):
        from alliance_platform.frontend.templatetags.react import CommonComponentSource
        from alliance_platform.frontend.templatetags.react import ComponentNode

        children = []
        for el in tree:
            if isinstance(el, str):
                parts = handle_placeholders(el)
                children += parts
            else:
                attrs, html_attribute_template_nodes = convert_attributes(el.attributes)
                children.append(
                    ComponentNode(
                        origin,
                        CommonComponentSource(el.tag),
                        {**attrs, "children": convert_tree(el.children)},
                        html_attribute_template_nodes=HtmlAttributeTemplateNodeList(
                            html_attribute_template_nodes, html, origin
                        ),
                    )
                )
        return children

    return convert_tree(tags)


def transform_html_attributes(attrs: dict[str, str | None], original_html: str, origin: Origin):
    """Transform the attributes of an HTML tag into the final form we want

    This does the following:
    - If any ``value`` is ``None``, set it to ``True`` if it's a boolean html attribute otherwise empty string
    - If any key is invalid, remove it and warn
    - Transform the attribute names to match what React expects
    """

    bad_keys: list[str] = []
    final_attrs = {}
    for key, value in attrs.items():
        if not is_valid_html_attribute_name(key):
            bad_keys.append(key)
        elif value is None:
            # for boolean attributes set it to ``True``, otherwise empty string
            final_attrs[key] = True if key in boolean_html_attributes else ""
        else:
            final_attrs[key] = value
    if bad_keys:
        warnings.warn(
            f"{origin} contained invalid HTML in '{original_html}'. The following parts were removed from tag: {', '.join(bad_keys)}"
        )
    return transform_attribute_names(final_attrs)
