import path from "node:path";

export const component = "inline_alert";
export const class_prefixes = ["InlineAlert", "Icon"];

export const stylesheets = [
  "@alliancesoftware/ui/components/inline-alert/InlineAlert.css.ts",
  "@alliancesoftware/icons/Icon.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  const load = (relativePath) =>
    importDefault(path.join(uiPackageDir, relativePath));
  return {
    InlineAlert: await load("components/inline-alert/InlineAlert.tsx"),
    Content: await load("components/layout/Content.tsx"),
    Heading: await load("components/layout/Heading.tsx"),
    Header: await load("components/layout/Header.tsx"),
    Footer: await load("components/layout/Footer.tsx"),
    AlertCircleOutlined: await load(
      "../icons/outlined/AlertCircleOutlined.tsx"
    ),
    AlertTriangleOutlined: await load(
      "../icons/outlined/AlertTriangleOutlined.tsx"
    ),
    CheckCircleOutlined: await load(
      "../icons/outlined/CheckCircleOutlined.tsx"
    ),
    InfoCircleOutlined: await load("../icons/outlined/InfoCircleOutlined.tsx"),
  };
}

// React's useHasChild only detects an alert holding nothing but content after mount, so SSR never
// marks it; the static renderer knows at render time. Mark the SSR output the same way.
export function normalize(root, testCase, helpers) {
  const alertRoot = root.querySelector('[data-apui="inline-alert"]');
  const alertInner = alertRoot?.firstElementChild;
  if (!alertRoot || !alertInner) {
    return;
  }
  const contentChildren = Array.from(alertInner.children).filter(
    (child) => !child.hasAttribute("data-alerticon")
  );
  if (
    contentChildren.length === 1 &&
    contentChildren[0].tagName === "SECTION" &&
    helpers
      .tokenizeClasses(contentChildren[0].getAttribute("class"))
      .some((token) => token.startsWith("InlineAlert_content"))
  ) {
    alertRoot.setAttribute("data-only-content", "true");
    alertInner.classList.add("InlineAlert_onlyContent");
  }
  helpers.normalizeInlineStyles(root);
}

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
