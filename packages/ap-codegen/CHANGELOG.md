# alliance-platform-codegen

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
