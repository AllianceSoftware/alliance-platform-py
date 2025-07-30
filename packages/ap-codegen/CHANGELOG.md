# alliance-platform-codegen

## 0.0.8

### Patch Changes

- 2844c8a: Make codegen detection of when to abort more robust. This helps avoid cases where codegen runs mid server restart and the git head changes which can produce incorrect changes.

## 0.0.7

### Patch Changes

- ee3ea1c: Add `RawNode` to codegen to support outputing code directly
- c8ef3b6: Fix code generated for embedding with <script> tags to properly escape code and avoid XSS vulnerabilities. This affected the `{% component %}` tag.

## 0.0.6

### Patch Changes

- 8ce1fa5: Fix type on `AlliancePlatformCodegenSettingsType.POST_PROCESSORS`; it should be either a string (the module import path) or a list of `ArtifactPostProcessor` instances.

## 0.0.5

### Patch Changes

- 2763b74: Properly handle comments within JSX attributes like `<Input description={/* comment here */<Inner />} />`

## 0.0.4

### Patch Changes

- 2947a19: Support for JSX in `TypescriptPrinter`, comments on nodes, and better handling of strings to avoid unnecessary conversion to ASCII.

## 0.0.3

### Patch Changes

- 93b6760: Fix codegen setting POST_PROCESSOR type

## 0.0.2

### Patch Changes

- 5fe0b38: Add AppConfig for codegen app
