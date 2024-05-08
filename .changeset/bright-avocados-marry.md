---
"alliance-platform-frontend": patch
---

Support LazyObject as a prop. This will unwrap the lazy object; the underlying value must be a valid prop type otherwise an error will be thrown. This allows things like the default `csrf_token` context variable to be passed.
