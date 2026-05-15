---
"alliance-platform-ui": patch
---

Fix two latent bundling issues where components referenced dynamically at render time were not statically discoverable, so could be omitted from the production frontend bundle:

- `InlineAlert` wraps plain-string children in a `Content` component.
- `form_input` wraps the widget in a `LabeledInput` component when `non_standard_widget=True`.

Both dependencies are now registered for bundling at parse time.
