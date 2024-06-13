# alliance-platform-frontend

## 0.0.12

### Patch Changes

- 99e73ac: FrontendAssetRegistry.lock will now only warn rather than throw an error if invalid values are used. This only occurs when DEBUG is True. This is to better accomodate configurations where node_modules might not be available (e.g. having DEBUG on in CI, but node_modules not installed).
- b28d46d: `{% component %}` tag will now only convert prop names from `this_case` to `thisCase`. Previously this was converting nested dicts as well - so things like `{ MY_CONSTANT: 5}` became `{ MYCONSTANT: 5}`.

## 0.0.11

### Patch Changes

- f92e443: Handle error with FrontendAssetRegistry that could occur in test cases when @modify_settings is used

## 0.0.10

### Patch Changes

- ce4f612: Fix issue where associated CSS for a nested component wasn't being embedded
- 8f3fb4b: Add classmethod `get_paths_for_bundling` to `ComponentProp`. This allows a handler to specify what dependencies they have that need to be included by the bundler. Previously this was done manually using `FrontendAssetRegistry"
- d3eea6f: TimeProp, DateTimeProp, DateProp, ZonedDateTimeProp no long use the frontend/src/re-exports.tsx file, and instead directly reference @internationalized/date
- 91835ae: Add `LabeledInput` template tag to `alliance_ui`
- ba4bb6f: Default `extra_widget_props` to empty dict if not set. This avoids need for widget templates to check for existence; it can rely on it being set so long as `FORM_RENDERED` is set. This allows widget templates to work when used with or without the `form_input` tag.
- 5c9efa7: `form_input` can now be used within `{% component %}` tags
- 5c9efa7: Add `non_standard_widget` option to `form_input`. This will wrap the widget in a `LabeledInput` to display label, help text, validation errors etc in same format as other alliance_ui widgets
- d606d99: alliance_ui tag `{% Fragment %}` no longer imports from re-exports and instead uses "react" directly. This removes the need for the frontend/src/re-exports file in projects and can be removed.

#### Upgrade instructions

See [this MR](https://gitlab.internal.alliancesoftware.com.au/alliance/template-django/-/merge_requests/495) for the relevant commits.

## 0.0.9

### Patch Changes

- e694c07: Fix so `renderComponent` on frontend doesn't try to hydrate SSR when SSR is explicitly disabled.
- 212737c: Perform asset registry checks in `lock`, and only when `DEBUG` is `True`. These checks do not need to happen in production, and could break things if you remove the frontend source code from the deployed files.

## 0.0.8

### Patch Changes

- 90317e4: Handle resolving template nodes used as props to raw html like `<a href="{% url "url-name" %}">...</a>`
- 46bbf31: Add `disable_ssr` option to `ViteBundler` to completely opt out of SSR

## 0.0.7

### Patch Changes

- cb83130: Properly handle nested HTML in template vars used with a {% component %} tag
- 401f503: Remove unneeded `raw_html` templatetag, and replace the use of the underlying `RawHtmlNode` in `form_input` templatetags
- e36d171: Adding stub documentation for Alliance UI templatetags

## 0.0.6

### Patch Changes

- e5725b6: Fix typing for `ComponentSourceCodeGenerator.add_leading_node`

## 0.0.5

### Patch Changes

- 2d8885b: Support LazyObject as a prop. This will unwrap the lazy object; the underlying value must be a valid prop type otherwise an error will be thrown. This allows things like the default `csrf_token` context variable to be passed.
- e2ee80d: Better handling for bundler dev server checks; avoid crashing on timeout, and handle false positive on dev server check on a read timeout.
- 8bf18f2: Support HTML directly within React components
- 00c8588: Add `DEV_CODE_FORMAT_LIMIT` to limit the size of code the dev server will attempt to format (default 1mb).
  Add `DEV_CODE_FORMAT_TIMEOUT` to control the timeout applied to requests to the Vite dev server for formatting; defaults to 1 second.
- e228296: React component tag codegen implementation has changed. To support latest changes, `REACT_RENDER_COMPONENT_FILE` should now export `createElement` from React directly; `createElementWithProps` is no longer used. `renderComponent` should accept an element to render rather than a component & props as separate arguments. SSR code should manually call `createElement` by extracting `children` from `props` and spreading them in the `createElement` call. Any custom `ComponentProp` classes can remove the `as_debug_string` method; it's no longer used.

## 0.0.4

### Patch Changes

- 0dbe111: Add `server_resolve_package_url` option to `ViteBundler`. This is used to resolve node_modules packages via the Vite dev server, rather than generating the URL ourselves. This behaves better with optimized deps and avoids a common case of "Outdated Optimized Deps" errors.

## 0.0.3

### Patch Changes

- e6fcaea: Add FRONTEND_ASSET_REGISTRY setting, remove default `frontend_asset_registry`

## 0.0.2

### Patch Changes

- 58839dc: Fix alliance_platform.frontend AppConfig to have a unique label
