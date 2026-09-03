---
"alliance-platform-ui": patch
---

Match React TextArea sizing in static templates by omitting legacy rows and cols attributes and
attaching the optional auto-grow runtime unless an explicit height is supplied. Re-export the
`none_as_nan` filter from the Alliance Platform UI template library for static number widgets.
