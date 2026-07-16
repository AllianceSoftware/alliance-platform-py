# alliance-platform-dev

Worktree-aware development runner for Alliance Platform Django projects.

Application developers use a checked-in `bin/dev` launcher. It obtains an exact, isolated package
version from PyPI with `uvx`, keeping the runner out of the application's Python environment.

Bootstrap an existing project with:

```bash
uvx --from alliance-platform-dev alliance-dev install
```

See the package documentation for installation, commands, configuration, and architecture.
