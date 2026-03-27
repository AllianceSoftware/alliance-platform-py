---
"alliance-platform-storage": patch
---

Add support for @alliancesoftware/ui/hook-form widget. This introduces some changes to the upload URL generation so widget can switch implementation based on backend requirements (e.g. POST vs PUT, form field requirements etc). These changes are additive to the API response so existing custom widgets should be compatible.
