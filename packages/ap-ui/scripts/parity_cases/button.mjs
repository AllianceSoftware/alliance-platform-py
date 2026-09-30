export const component = "button";
export const class_prefixes = ["focusRing", "Button", "Icon"];

export const cases = [
  {
    name: "default",
    template: '{% ui "button" %}Save{% endui %}',
    buildElement({ React, components }) {
      const { Button } = components;
      return React.createElement(Button, null, "Save");
    },
    meta: {},
  },
  {
    name: "invalid_variant_warns_and_falls_back",
    template: '{% ui "button" variant="invalid" %}Save{% endui %}',
    buildElement({ React, components }) {
      const { Button } = components;
      return React.createElement(Button, { variant: "invalid" }, "Save");
    },
    meta: {},
  },
  {
    name: "anchor_variant",
    template:
      '{% ui "button" href="/next" color="secondary" size="lg" %}Go{% endui %}',
    buildElement({ React, components }) {
      const { Button } = components;
      return React.createElement(
        Button,
        { href: "/next", color: "secondary", size: "lg" },
        "Go"
      );
    },
    meta: {},
  },
  {
    name: "disabled_anchor",
    template: '{% ui "button" href="/next" is_disabled=True %}Go{% endui %}',
    buildElement({ React, components }) {
      const { Button } = components;
      return React.createElement(
        Button,
        { href: "/next", isDisabled: true },
        "Go"
      );
    },
    meta: {},
  },
  {
    name: "explicit_raw_span_icon_only",
    preserve_icon_only: true,
    template:
      '{% ui "button" is_icon_only=True %}<span data-apui-slot="icon"></span>{% endui %}',
    buildElement({ React, components }) {
      const { Button } = components;
      return React.createElement(
        Button,
        { isIconOnly: true },
        React.createElement("span", { "data-apui-slot": "icon" })
      );
    },
    meta: {},
  },
  {
    name: "icon_only",
    preserve_icon_only: true,
    template:
      '{% ui "button" aria_label="Approve" %}' +
      '{% ui "icon" name="CheckOutlined" %}{% endui %}' +
      "{% endui %}",
    buildElement({ React, components }) {
      const { Button, CheckOutlined } = components;
      return React.createElement(
        Button,
        { "aria-label": "Approve" },
        React.createElement(CheckOutlined)
      );
    },
    meta: {},
  },
  {
    name: "icon_and_text",
    template:
      '{% ui "button" %}' +
      '{% ui "icon" name="CheckOutlined" %}{% endui %}' +
      "Approve" +
      "{% endui %}",
    buildElement({ React, components }) {
      const { Button, CheckOutlined } = components;
      return React.createElement(
        Button,
        null,
        React.createElement(CheckOutlined),
        "Approve"
      );
    },
    meta: {},
  },
];
