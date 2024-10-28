---
"alliance-platform-frontend": patch
---

Fix prop handlers for `Time`, `CalendarDateTime` and `ZonedDateTime` to convert microseconds to milliseconds. Javascript doesn't support microseconds, so convert to milliseconds.
