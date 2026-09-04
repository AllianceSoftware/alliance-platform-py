export const component = "inline_alert";
export const class_prefixes = ["InlineAlert", "Icon"];

export const cases = [
  {
    name: "default_loose_content",
    template: '{% ui "inline_alert" %}Saved successfully.{% endui %}',
    buildElement({ React, components }) {
      const { InlineAlert, Content, InfoCircleOutlined } = components;
      return React.createElement(
        InlineAlert,
        null,
        React.createElement(InfoCircleOutlined, null),
        React.createElement(Content, null, "Saved successfully.")
      );
    },
    meta: {},
  },
  {
    name: "danger_without_icon",
    template:
      '{% ui "inline_alert" intent="danger" hide_icon=True %}Try again.{% endui %}',
    buildElement({ React, components }) {
      const { InlineAlert, Content } = components;
      return React.createElement(
        InlineAlert,
        { intent: "danger", hideIcon: true },
        React.createElement(Content, null, "Try again.")
      );
    },
    meta: {},
  },
  {
    name: "danger_with_icon",
    template: '{% ui "inline_alert" intent="danger" %}Try again.{% endui %}',
    buildElement({ React, components }) {
      const { InlineAlert, Content, AlertCircleOutlined } = components;
      return React.createElement(
        InlineAlert,
        { intent: "danger" },
        React.createElement(AlertCircleOutlined, null),
        React.createElement(Content, null, "Try again.")
      );
    },
    meta: {},
  },
  {
    name: "explicit_content",
    template:
      '{% ui "inline_alert" intent="success" %}' +
      '{% ui "content" %}<p>Complete.</p>{% endui %}' +
      "{% endui %}",
    buildElement({ React, components }) {
      const { InlineAlert, Content, CheckCircleOutlined } = components;
      return React.createElement(
        InlineAlert,
        { intent: "success" },
        React.createElement(CheckCircleOutlined, null),
        React.createElement(
          Content,
          null,
          React.createElement("p", null, "Complete.")
        )
      );
    },
    meta: {},
  },
  {
    name: "structured_content",
    template:
      '{% ui "inline_alert" intent="warning" %}' +
      '{% ui "heading" %}Check this{% endui %}' +
      '{% ui "header" %}Before continuing{% endui %}' +
      '{% ui "content" %}Review the details.{% endui %}' +
      '{% ui "footer" %}You can return later.{% endui %}' +
      "{% endui %}",
    buildElement({ React, components }) {
      const {
        InlineAlert,
        Content,
        Heading,
        Header,
        Footer,
        AlertTriangleOutlined,
      } = components;
      return React.createElement(
        InlineAlert,
        { intent: "warning" },
        React.createElement(AlertTriangleOutlined, null),
        React.createElement(Heading, null, "Check this"),
        React.createElement(Header, null, "Before continuing"),
        React.createElement(Content, null, "Review the details."),
        React.createElement(Footer, null, "You can return later.")
      );
    },
    meta: {},
  },
  {
    name: "root_attributes",
    template:
      '{% ui "inline_alert" class="custom-alert" style="max-width: 400px" ' +
      'id="status" data_testid="status" aria_live="polite" %}Status{% endui %}',
    buildElement({ React, components }) {
      const { InlineAlert, Content, InfoCircleOutlined } = components;
      return React.createElement(
        InlineAlert,
        {
          className: "custom-alert",
          style: { maxWidth: "400px" },
          id: "status",
          "data-testid": "status",
          "aria-live": "polite",
        },
        React.createElement(InfoCircleOutlined, null),
        React.createElement(Content, null, "Status")
      );
    },
    meta: {},
  },
];
