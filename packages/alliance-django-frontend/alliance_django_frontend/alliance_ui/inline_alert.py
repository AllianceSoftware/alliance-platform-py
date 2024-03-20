from django import template
from django.template import Context
from django.template import Library

from common_frontend.alliance_ui.utils import get_module_import_source
from common_frontend.templatetags.react import ComponentNode
from common_frontend.templatetags.react import ComponentProps
from common_frontend.templatetags.react import NestedComponentProp
from common_frontend.templatetags.react import parse_component_tag


class InlineAlertNode(ComponentNode):
    def resolve_props(self, context: Context) -> ComponentProps:
        props = super().resolve_props(context)
        # If only a string is passed as child then wrap it in a <Content> component
        children = props.props.get("children")
        if isinstance(children, str):
            props.props["children"] = NestedComponentProp(
                ComponentNode(
                    self.origin,
                    get_module_import_source("@alliancesoftware/ui", "Content", False, self.origin),
                    {"children": children},
                ),
                self,
                context,
            )
        return props


def inline_alert(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        node_class=InlineAlertNode,
        asset_source=get_module_import_source("@alliancesoftware/ui", "InlineAlert", False, parser.origin),
    )


def register_inline_alert(register: Library):
    register.tag("InlineAlert")(inline_alert)
