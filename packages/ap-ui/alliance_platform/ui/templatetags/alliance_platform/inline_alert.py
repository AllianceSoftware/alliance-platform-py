from django import template
from django.template import Context
from django.template import Library

from alliance_platform.frontend.templatetags.react import ComponentNode
from alliance_platform.frontend.templatetags.react import ComponentProps
from alliance_platform.frontend.templatetags.react import NestedComponentProp
from alliance_platform.frontend.templatetags.react import parse_component_tag

from .utils import get_module_import_source


class InlineAlertNode(ComponentNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ``Content`` is wrapped around plain-string children at render time, so it is not
        # statically discoverable. Always include it in the bundle so it is available.
        self._content_source = get_module_import_source("@alliancesoftware/ui", "Content", False, self.origin)

    def get_resources_for_bundling(self):
        resources = super().get_resources_for_bundling()
        resources.append(self._content_source.create_frontend_resource(self.bundler))
        return resources

    def resolve_props(self, context: Context) -> ComponentProps:
        props = super().resolve_props(context)
        # If only a string is passed as child then wrap it in a <Content> component
        children = props.props.get("children")
        if isinstance(children, str):
            props.props["children"] = NestedComponentProp(
                ComponentNode(
                    self.origin,
                    self._content_source,
                    {"children": children},
                ),
                self,
                context,
            )
        return props


def inline_alert(parser: template.base.Parser, token: template.base.Token):
    """Render an ``InlineAlert`` component from the Alliance UI React library with the specified props."""
    return parse_component_tag(
        parser,
        token,
        node_class=InlineAlertNode,
        asset_source=get_module_import_source("@alliancesoftware/ui", "InlineAlert", False, parser.origin),
    )


def register_inline_alert(register: Library):
    register.tag("InlineAlert")(inline_alert)
