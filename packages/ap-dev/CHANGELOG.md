# alliance-platform-dev

## 0.0.3

### Patch Changes

- f112bea: Exit with status 1 from `alliance-dev doctor` when any check reports an error, and end the text output with a summary of errors and warnings.
- f112bea: Add `.dev-server/` to the project `.gitignore` during `alliance-dev install` unless an existing entry already ignores it.
- 5f54919: Store generated launcher environments in a durable user cache when writable, check cached entry
  points offline, and rotate and rebuild incomplete bootstrap environments before running commands.
  Add `alliance-dev update-launcher` so existing projects can adopt the fix without rerunning the
  interactive installer:

  ```bash
  uvx --upgrade --from alliance-platform-dev alliance-dev update-launcher
  ```

- f112bea: Include `schemaVersion` in `alliance-dev url --json` output, matching the other JSON commands.

## 0.0.2

### Patch Changes

- 951f657: Pass trailing command-line arguments through `alliance-dev check` to the configured check command.

## 0.0.1

### Patch Changes

- 82e19a4: Add the Alliance Platform worktree-aware development runner, including an interactive installer. See the
  [documentation](https://alliance-platform.readthedocs.io/projects/dev/latest/) for more details.
