export const component = "pagination";
export const class_prefixes = ["Pagination", "Button", "focusRing", "Icon"];

export const stylesheets = [
  "@alliancesoftware/ui/components/pagination/Pagination.css.ts",
  "@alliancesoftware/ui/components/button/Button.css.ts",
  "@alliancesoftware/ui/styles/base/focusRing.css.ts",
  "@alliancesoftware/icons/Icon.css.ts",
];

export async function loadComponents({ importBareModule }) {
  const paginationModule = await importBareModule(
    "@alliancesoftware/ui/components/pagination/Pagination"
  );
  return {
    Pagination: paginationModule.default,
    renderPaginationItemAsLink: paginationModule.renderPaginationItemAsLink,
  };
}

// The static side's own extensions (the medium and small responsive ranges, tabindex on disabled
// links) are stripped by strip_static_pagination_extensions() in
// tests/test_html_ui_pagination_parity.py; see DEVELOPMENT.md for the full list.
export function normalize(root, testCase, helpers) {
  // Every control is a Button rendered as a link.
  helpers.normalizeButtons(root, testCase);
  for (const element of helpers.elements(root)) {
    // renderPaginationItemAsLink builds absolute URLs from currentUrl; the static renderer writes
    // the path and query only.
    const href = element.getAttribute("href");
    if (href?.startsWith("http://testserver")) {
      element.setAttribute("href", href.slice("http://testserver".length));
    }
    // PaginationItem passes a boolean, so every page link gets aria-current="true" or "false";
    // the static renderer marks only the current page, with the "page" token.
    const ariaCurrent = element.getAttribute("aria-current");
    if (ariaCurrent === "false") {
      element.removeAttribute("aria-current");
    } else if (ariaCurrent === "true") {
      element.setAttribute("aria-current", "page");
    }
  }
}

// The static renderer renders every control as a link, like React's renderPaginationItemAsLink.
// The links are built from the URL in meta.current_url, which the Python test requests.
function paginationCase({ name, template, props, currentUrl }) {
  return {
    name,
    template,
    buildElement({ React, components }) {
      const { Pagination, renderPaginationItemAsLink } = components;
      return React.createElement(Pagination, {
        "aria-label": "Pagination",
        ...props,
        renderItem: renderPaginationItemAsLink,
        renderItemProps: {
          currentUrl: new URL(currentUrl, "http://testserver").toString(),
        },
      });
    },
    meta: { current_url: currentUrl },
  };
}

export const cases = [
  paginationCase({
    name: "middle_page_default_counts",
    template:
      '{% ui "pagination" page=10 total=200 page_size=10 aria_label="Pagination" %}',
    props: { page: 10, total: 200, pageSize: 10 },
    currentUrl: "/users/?ordering=name&page=10",
  }),
  paginationCase({
    name: "first_page",
    template:
      '{% ui "pagination" page=1 total=200 page_size=10 aria_label="Pagination" %}',
    props: { page: 1, total: 200, pageSize: 10 },
    currentUrl: "/users/",
  }),
  paginationCase({
    name: "last_page",
    template:
      '{% ui "pagination" page=20 total=200 page_size=10 aria_label="Pagination" %}',
    props: { page: 20, total: 200, pageSize: 10 },
    currentUrl: "/users/?page=20",
  }),
  paginationCase({
    name: "compact_variant",
    template:
      '{% ui "pagination" page=2 total=50 page_size=10 variant="compact" aria_label="Pagination" %}',
    props: { page: 2, total: 50, pageSize: 10, variant: "compact" },
    currentUrl: "/users/?page=2",
  }),
  paginationCase({
    name: "size_md",
    template:
      '{% ui "pagination" page=2 total=50 page_size=10 size="md" aria_label="Pagination" %}',
    props: { page: 2, total: 50, pageSize: 10, size: "md" },
    currentUrl: "/users/?page=2",
  }),
  paginationCase({
    name: "disabled",
    template:
      '{% ui "pagination" page=2 total=50 page_size=10 is_disabled=True aria_label="Pagination" %}',
    props: { page: 2, total: 50, pageSize: 10, isDisabled: true },
    currentUrl: "/users/?page=2",
  }),
];
