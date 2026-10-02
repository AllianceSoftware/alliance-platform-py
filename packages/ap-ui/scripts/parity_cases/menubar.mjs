import path from "node:path";

export const component = "menubar";
export const class_prefixes = ["Menubar", "Icon"];

export const stylesheets = [
  "@alliancesoftware/ui/components/menu-bar/Menubar.css.ts",
  "@alliancesoftware/ui/components/overlay/Popover.css.ts",
  "@alliancesoftware/icons/Icon.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  const Menubar = await importDefault(
    path.join(uiPackageDir, "components/menu-bar/Menubar.tsx")
  );
  return {
    Menubar,
    Item: Menubar.Item,
    SubMenu: Menubar.SubMenu,
    Section: Menubar.Section,
    Pencil01Outlined: await importDefault(
      path.join(uiPackageDir, "../icons/outlined/Pencil01Outlined.tsx")
    ),
  };
}

// The static side's own extensions are stripped by strip_static_menubar_extensions() in
// tests/test_html_ui_menubar_parity.py; see DEVELOPMENT.md for the full list.
export function normalize(root, testCase, helpers) {
  // React SSRs an offscreen "more items" node to measure overflow.
  root.querySelector('li[data-key="____more_items_from_overflow"]')?.remove();
  for (const element of helpers.elements(root)) {
    for (const attribute of [
      "tabindex",
      "data-key",
      "data-collection",
      "data-has-leading-icon",
    ]) {
      element.removeAttribute(attribute);
    }
    if (element.getAttribute("aria-disabled") === "false") {
      element.removeAttribute("aria-disabled");
    }
    if (element.getAttribute("aria-hidden") === "false") {
      element.removeAttribute("aria-hidden");
    }
    // React emits hasLeadingIcon optimistically during SSR, before useHasChild inspects the DOM.
    if (element.hasAttribute("class")) {
      element.classList.forEach((token) => {
        if (/^Menubar_hasLeadingIcon__/.test(token)) {
          element.classList.remove(token);
        }
      });
      if (!element.className) {
        element.removeAttribute("class");
      }
    }
  }
  helpers.normalizeCssVarHashes(root);

  // Section headings label their groups, so referenced ids survive and are remapped.
  const referenced = helpers.collectReferencedReactAriaIds(root, [
    "for",
    "aria-controls",
    "aria-labelledby",
    "aria-describedby",
    "aria-errormessage",
  ]);
  helpers.removeUnreferencedReactAriaIds(root, referenced);
  helpers.remapReactAriaIds(root, component);
  for (const icon of root.querySelectorAll('[role="img"]')) {
    icon.setAttribute("data-apui-slot", "icon");
  }
}

// The static renderer's popup wrappers (hidden popovers / inline menus) and runtime wiring are
// static extensions the React SSR output cannot contain (React renders open menus in a portal,
// closed menus not at all). Those parts are stripped by the Python parity test's normalisation
// and covered by unit tests; genuine content parity for submenu menus comes from the
// layout="inline" + defaultExpandedKeys cases below, which React renders inline during SSR.
//
// Submenu triggers default to <div> in React when no href is given; the static renderer uses
// <button> so menus are focusable/activatable without React. Cases pass elementType="button"
// explicitly on the React side so the trigger markup is comparable.

function buildMenubar({ React, components }, menubarProps, children) {
  const { Menubar } = components;
  return React.createElement(
    Menubar,
    { "aria-label": "Nav", ...menubarProps },
    ...children
  );
}

export const cases = [
  {
    name: "basic_horizontal_links",
    template:
      '{% ui "menubar" aria_label="Nav" %}' +
      '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}' +
      '{% ui "menubar_item" href="/users/" %}Users{% endui %}' +
      '{% ui "menubar_item" href="/audit/" %}Audit{% endui %}' +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item } = components;
      return buildMenubar(runtime, {}, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/" },
          "Dashboard"
        ),
        React.createElement(Item, { key: "users", href: "/users/" }, "Users"),
        React.createElement(Item, { key: "audit", href: "/audit/" }, "Audit"),
      ]);
    },
    meta: {},
  },
  {
    name: "vertical_links",
    template:
      '{% ui "menubar" aria_label="Nav" layout="vertical" %}' +
      '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}' +
      '{% ui "menubar_item" href="/audit/" %}Audit{% endui %}' +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item } = components;
      return buildMenubar(runtime, { layout: "vertical" }, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/" },
          "Dashboard"
        ),
        React.createElement(Item, { key: "audit", href: "/audit/" }, "Audit"),
      ]);
    },
    meta: {},
  },
  {
    name: "icon_only_root_items",
    template:
      '{% ui "menubar" aria_label="Nav" layout="vertical" root_item_display="icon-only" %}' +
      '{% ui "menubar_item" href="/dashboard/" text_value="Dashboard" %}' +
      '{% ui "icon" name="Pencil01Outlined" %}{% endui %}Dashboard' +
      "{% endui %}" +
      '{% ui "menubar_submenu" key="admin" title="Administration" icon="Pencil01Outlined" %}' +
      '{% ui "menubar_item" href="/users/" %}Users{% endui %}' +
      "{% endui %}" +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item, SubMenu, Pencil01Outlined } = components;
      return buildMenubar(
        runtime,
        { layout: "vertical", rootItemDisplay: "icon-only" },
        [
          React.createElement(
            Item,
            { key: "dashboard", href: "/dashboard/", textValue: "Dashboard" },
            React.createElement(Pencil01Outlined),
            "Dashboard"
          ),
          React.createElement(
            SubMenu,
            {
              key: "admin",
              title: React.createElement(
                React.Fragment,
                null,
                React.createElement(Pencil01Outlined),
                "Administration"
              ),
              textValue: "Administration",
              elementType: "button",
            },
            React.createElement(
              Item,
              { key: "users", href: "/users/" },
              "Users"
            )
          ),
        ]
      );
    },
    meta: {},
  },
  {
    name: "inline_links",
    template:
      '{% ui "menubar" aria_label="Nav" layout="inline" %}' +
      '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}' +
      '{% ui "menubar_item" href="/audit/" %}Audit{% endui %}' +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item } = components;
      return buildMenubar(runtime, { layout: "inline" }, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/" },
          "Dashboard"
        ),
        React.createElement(Item, { key: "audit", href: "/audit/" }, "Audit"),
      ]);
    },
    meta: {},
  },
  {
    name: "submenu_flyout_closed",
    template:
      '{% ui "menubar" aria_label="Nav" %}' +
      '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}' +
      '{% ui "menubar_submenu" key="users" title="Users" %}' +
      '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}' +
      '{% ui "menubar_item" href="/customers/" %}Customers{% endui %}' +
      "{% endui %}" +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item, SubMenu } = components;
      return buildMenubar(runtime, {}, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/" },
          "Dashboard"
        ),
        React.createElement(
          SubMenu,
          { key: "users", title: "Users", elementType: "button" },
          React.createElement(Item, { key: "admin", href: "/admin/" }, "Admin"),
          React.createElement(
            Item,
            { key: "customers", href: "/customers/" },
            "Customers"
          )
        ),
      ]);
    },
    meta: {},
  },
  {
    name: "submenu_inline_expanded",
    template:
      '{% ui "menubar" aria_label="Nav" layout="inline" default_expanded_keys="users" %}' +
      '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}' +
      '{% ui "menubar_submenu" key="users" title="Users" %}' +
      '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}' +
      '{% ui "menubar_item" href="/customers/" %}Customers{% endui %}' +
      "{% endui %}" +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item, SubMenu } = components;
      return buildMenubar(
        runtime,
        { layout: "inline", defaultExpandedKeys: ["users"] },
        [
          React.createElement(
            Item,
            { key: "dashboard", href: "/dashboard/" },
            "Dashboard"
          ),
          React.createElement(
            SubMenu,
            { key: "users", title: "Users", elementType: "button" },
            React.createElement(
              Item,
              { key: "admin", href: "/admin/" },
              "Admin"
            ),
            React.createElement(
              Item,
              { key: "customers", href: "/customers/" },
              "Customers"
            )
          ),
        ]
      );
    },
    meta: {},
  },
  {
    name: "nested_submenu_inline_expanded",
    template:
      '{% ui "menubar" aria_label="Nav" layout="inline" default_expanded_keys="users,reports" %}' +
      '{% ui "menubar_submenu" key="users" title="Users" %}' +
      '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}' +
      '{% ui "menubar_submenu" key="reports" title="Reports" %}' +
      '{% ui "menubar_item" href="/reports/weekly/" %}Weekly{% endui %}' +
      "{% endui %}" +
      "{% endui %}" +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item, SubMenu } = components;
      return buildMenubar(
        runtime,
        { layout: "inline", defaultExpandedKeys: ["users", "reports"] },
        [
          React.createElement(
            SubMenu,
            { key: "users", title: "Users", elementType: "button" },
            React.createElement(
              Item,
              { key: "admin", href: "/admin/" },
              "Admin"
            ),
            React.createElement(
              SubMenu,
              { key: "reports", title: "Reports", elementType: "button" },
              React.createElement(
                Item,
                { key: "weekly", href: "/reports/weekly/" },
                "Weekly"
              )
            )
          ),
        ]
      );
    },
    meta: {},
  },
  {
    name: "section_with_title_and_separator",
    template:
      '{% ui "menubar" aria_label="Nav" layout="inline" %}' +
      '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}' +
      '{% ui "menubar_section" title="Tools" class="custom-section" separator_class_name="custom-separator" %}' +
      '{% ui "menubar_item" href="/audit/" %}Audit{% endui %}' +
      "{% endui %}" +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item, Section } = components;
      return buildMenubar(runtime, { layout: "inline" }, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/" },
          "Dashboard"
        ),
        React.createElement(
          Section,
          {
            key: "tools",
            title: "Tools",
            className: "custom-section",
            separatorClassName: "custom-separator",
          },
          React.createElement(Item, { key: "audit", href: "/audit/" }, "Audit")
        ),
      ]);
    },
    meta: {},
  },
  {
    name: "button_item_form_submit",
    template:
      '{% ui "menubar" aria_label="Nav" %}' +
      '{% ui "menubar_item" element_type="button" type="submit" form="logout-form" %}Logout{% endui %}' +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item } = components;
      return buildMenubar(runtime, {}, [
        React.createElement(
          Item,
          {
            key: "logout",
            elementType: "button",
            type: "submit",
            form: "logout-form",
          },
          "Logout"
        ),
      ]);
    },
    meta: {},
  },
  {
    name: "disabled_item",
    template:
      '{% ui "menubar" aria_label="Nav" %}' +
      '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}' +
      '{% ui "menubar_item" href="/secret/" is_disabled=True %}Secret{% endui %}' +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item } = components;
      return buildMenubar(runtime, { disabledKeys: ["secret"] }, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/" },
          "Dashboard"
        ),
        React.createElement(
          Item,
          { key: "secret", href: "/secret/" },
          "Secret"
        ),
      ]);
    },
    meta: {},
  },
  {
    name: "current_item",
    template:
      '{% ui "menubar" aria_label="Nav" %}' +
      '{% ui "menubar_item" href="/dashboard/" is_current=True %}Dashboard{% endui %}' +
      '{% ui "menubar_item" href="/audit/" %}Audit{% endui %}' +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item } = components;
      return buildMenubar(runtime, {}, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/", "aria-current": "page" },
          "Dashboard"
        ),
        React.createElement(Item, { key: "audit", href: "/audit/" }, "Audit"),
      ]);
    },
    meta: {},
  },
  {
    name: "rich_item_content_with_text_value",
    template:
      '{% ui "menubar" aria_label="Nav" %}' +
      '{% ui "menubar_item" href="/reports/" text_value="Reports" %}<b>Reports</b>{% endui %}' +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item } = components;
      return buildMenubar(runtime, {}, [
        React.createElement(
          Item,
          { key: "reports", href: "/reports/", textValue: "Reports" },
          React.createElement("b", null, "Reports")
        ),
      ]);
    },
    meta: {},
  },
  {
    name: "class_merge",
    template:
      '{% ui "menubar" aria_label="Nav" class="custom-menubar" %}' +
      '{% ui "menubar_item" href="/dashboard/" class="custom-item" %}Dashboard{% endui %}' +
      '{% ui "menubar_submenu" key="users" title="Users" class="custom-trigger" %}' +
      '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}' +
      "{% endui %}" +
      "{% endui %}",
    buildElement(runtime) {
      const { React, components } = runtime;
      const { Item, SubMenu } = components;
      return buildMenubar(runtime, { className: "custom-menubar" }, [
        React.createElement(
          Item,
          { key: "dashboard", href: "/dashboard/", className: "custom-item" },
          "Dashboard"
        ),
        React.createElement(
          SubMenu,
          {
            key: "users",
            title: "Users",
            elementType: "button",
            className: "custom-trigger",
          },
          React.createElement(Item, { key: "admin", href: "/admin/" }, "Admin")
        ),
      ]);
    },
    meta: {},
  },
];
