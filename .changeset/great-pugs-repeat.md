---
"alliance-platform-ui": patch
---

Add HTML dispatcher renderers for `text_input`, `number_input` and `text_area`, available through `{% ui "text_input" ... %}` etc. These mirror the `@alliancesoftware/ui` `TextInput`, `NumberInput` and `TextArea` components (LabeledInput/TextInputBase markup, data-attribute driven state, static validation icons and number step buttons) without client-side behaviour.
