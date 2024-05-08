---
"alliance-platform-frontend": patch
---

React component tag codegen implementation has changed. To support latest changes, `REACT_RENDER_COMPONENT_FILE` should now export `createElement` from React directly; `createElementWithProps` is no longer used. `renderComponent` should accept an element to render rather than a component & props as separate arguments. SSR code should manually call `createElement` by extracting `children` from `props` and spreading them in the `createElement` call. Any custom `ComponentProp` classes can remove the `as_debug_string` method; it's no longer used.
