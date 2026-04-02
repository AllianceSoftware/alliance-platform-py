# alliance-platform-storage

## 0.0.5

### Patch Changes

- 4d8a232: `AsyncFileField` form field now supports `has_changed`, enabling correct `Form.has_changed()` behavior.
- 6451dba: Add support for @alliancesoftware/ui/hook-form widget. This introduces some changes to the upload URL generation so widget can switch implementation based on backend requirements (e.g. POST vs PUT, form field requirements etc). These changes are additive to the API response so existing custom widgets should be compatible.

## 0.0.4

### Patch Changes

- c7266ea: Add support for `download_params` to AsyncFileField & AsyncImageField

## 0.0.3

### Patch Changes

- e39cd9c: Update `AzureUploadStorage` to support managed identity authentication

## 0.0.2

### Patch Changes

- 5bd848f: Initial release of [alliance_platform_storage](https://alliance-platform.readthedocs.io/projects/storage)
