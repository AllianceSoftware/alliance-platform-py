# Alliance Platform Python

A collection of Python packages for use in the Alliance Platform Django template.

Documentation: https://alliance-platform.readthedocs.io/

## Packages

- [Core](packages/ap-core) ([Documentation](https://alliance-platform.readthedocs.io/en/latest/core.html))
- [Frontend](packages/ap-frontend) ([Documentation](https://alliance-platform.readthedocs.io/projects/frontend/latest/))
- [Codegen](packages/ap-codegen) ([Documentation](https://alliance-platform.readthedocs.io/projects/codegen/latest/))
- [Storage](packages/ap-storage) ([Documentation](https://alliance-platform.readthedocs.io/projects/storage/latest/))
- [Audit](packages/ap-audit) ([Documentation](https://alliance-platform.readthedocs.io/projects/audit/latest/))
- [UI](packages/ap-ui) ([Documentation](https://alliance-platform.readthedocs.io/projects/ui/latest/))
- [PDF](packages/ap-pdf) ([Documentation](https://alliance-platform.readthedocs.io/projects/pdf/latest/))
- [Server Choices](packages/ap-server-choices) ([Documentation](https://alliance-platform.readthedocs.io/projects/server-choices/latest/))
- [Ordered Model](packages/ap-ordered-model) ([Documentation](https://alliance-platform.readthedocs.io/projects/ordered-model/latest/))

## Development Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 20+ (for frontend tooling)
- (Optional) [just](https://github.com/casey/just) for convenient task running

### Installation

```bash
uv sync
# Setup git hooks and changesets, node_modules used for some tests
yarn
```

**Notes:**
- This project uses **uv** for dependency management and **uv workspaces** with a single shared virtual environment for all packages during development. CI testing enforces true package isolation by testing each package separately.
- Package building uses **pdm-backend** as the build backend. This is a standalone PEP 517-compliant build backend that works with any build tool (including uv) and does not require PDM to be installed. The `[tool.pdm.*]` sections in package `pyproject.toml` files are configuration for pdm-backend, not the PDM tool itself.

### Project Structure

The project is structured as a monorepo, with each package in the `packages` directory. As a convention, each package
in here is named `ap-<name>`; this was chosen so it's not a valid python package name and is distinct from the underlying
package for ease of navigation / searching.

Each package has a [namespaced package](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/) called `alliance_platform`, and
then within that the specific package name (e.g. `frontend` or `codegen`). This allows all Alliance Platform packages
to be imported from `alliance_platform` while being released and versioned independently.

## Running Tests

### Test a Single Package

```bash
# Default Python version (3.11 from .python-version)
just test-package ap-pdf

# Specific Python version
just test-package ap-pdf 3.12

# With Django constraint (matches CI behavior)
just test-package ap-pdf 3.12 django42  # Django 4.2.x
just test-package ap-pdf 3.12 django52  # Django 5.2.x
```

### Test All Packages

```bash
# Default Python version
just test-all

# Specific Python version
just test-all 3.13

# With Django constraint (matches CI behavior)
just test-all 3.12 django42  # Test all packages with Python 3.12 + Django 4.2
just test-all 3.12 django52  # Test all packages with Python 3.12 + Django 5.2
```

**Tip:** Use the constraint parameter to test locally with the same Django versions as CI!

### Run Tests with Coverage

```bash
cd packages/ap-pdf
uv run coverage run --source=alliance_platform ./manage.py test
uv run coverage report
```

## Managing Dependencies

### Workspace Structure

This is a monorepo with packages in `packages/`. Each package has its own `pyproject.toml` but shares a single workspace-level `uv.lock` file.

### Adding Dependencies

**For runtime dependencies:**

```toml
# packages/ap-pdf/pyproject.toml
[project]
dependencies = [
    "playwright",
    "Django>=4.2.11",
]
```

**For development/test dependencies:**

```toml
# packages/ap-pdf/pyproject.toml
[dependency-groups]
dev = [
    "factory-boy",           # For test factories
    "alliance-platform-frontend",  # If testing integration with another package
]
```

After modifying dependencies:

```bash
uv sync  # Updates uv.lock
```

## Other Commands

### Linting & Code Formatting

This is handled by `ruff`, and should automatically be run on commit. You can run it manually:

```bash
just lint          # Run ruff linter
just format        # Format code with ruff
just format-check  # Check formatting without changes

# Without just:
uv run ruff check
uv run ruff check --fix
uv run ruff format
```

### Type Checking

```bash
just mypy-all      # Type check all packages
just mypy-package ap-pdf  # Type check specific package

# Without just:
cd packages/ap-pdf && uv run mypy .
```

### Documentation

Build the documentation for all packages, serve it locally, and watch for changes:

```bash
just docs-watch
```

### CI/CD

CI runs parallel test jobs using GitHub Actions. Each job:

1. Installs package-specific dependencies with `uv sync --package`
2. Conditionally installs Playwright (only for packages that need it)
3. Runs tests with coverage
4. Uploads coverage to Codecov

## Contributing

### Release process

When a change is made that requires a release the following workflow applies:

1. Run `yarn changeset`. Select the packages that have changed and the type of change (major, minor, patch). Add a description of the change.
2. This will create a new changeset file in the `.changeset` directory. You can modify this file if needed to adjust the description.
3. Commit the changeset file and open a pull request.
4. Once the PR is merged, a GitHub action will automatically create a PR to bump the version and publish the package to PyPI. If such a PR
   exists already, it will be updated with the new changeset.
5. When that PR is merged, the package will be published to PyPI.

### Adding a new package

To add a new package, create a directory in `packages/` named `ap-<name>`. It should contain a `pyproject.toml` file and
a `package.json` file; base these off the existing packages.

1. Create a `pyproject.toml file`. This is relatively straightforward, but you can base it off the existing packages.
2. Create a `package.json` file. This is only required so that `changesets` knows a package exists to be versioned, and to
   store the version number. You just need to set the `name` here and choose the initial `version`.
3. Create the structure of the package like other packages; a namespaced `alliance_platform` package, and then the specific
   package name (e.g. `frontend` or `codegen`).
4. Create a test app for the project, you can see `ap-frontend/test_alliance_platform_frontend` for an example.
5. Create a `manage.py` file based on an existing package, and update `"DJANGO_SETTINGS_MODULE"`.
6. Update `.github/workflows/ci.yml` to add the new package to the matrix of jobs.
7. In GitHub a new token for publishing will be needed. It should be added to the [release environment secrets](https://github.com/AllianceSoftware/alliance-platform-py/settings/environments/2665697079/edit)
   as `ALLIANCE_PLATFORM_<upper case package name>_TOKEN`. To create the token, go to [PyPI](https://pypi.org/manage/account/token/) and create a new token. The
   scope should be for the specific package only - if the package hasn't been published yet you can create one for all packages but
   you must re-create it after the initial publish and limit it to the specific package scope. Note that the PyPi Trusted Publishers
   would be good for this but I couldn't work out how to re-purpose it for our publishing workflow.
   1. Update `.github/workflows/release.yml` and add the token under the `env` for the `Create Release Pull Request or Publish to pypi` step.
8. Create a `docs` dir, see existing package for an example.
   1. Create an entry in `docs/conf.py` under `multiproject_projects` for the new package.
   2. In readthedocs.org, a new project needs to be created. To do this, import the <https://github.com/AllianceSoftware/alliance-platform-py> repo
      again, but name it according to the package name (`alliance-platform-<name>`).
   3. Under the new project, go to Settings and Environment Variables. Add a new variable `PROJECT` and name it the same as
      what the key in `multiple_projects` is. Check the 'Public' checkbox so it can be used in pull requests.
   4. Go to Automation Rules and add a rule for detecting version tags. Set it to a custom match on tags with the pattern `alliance-platform-NAME@\d\.\d\.\d` (where NAME is replaced with the package name)
   5. Under settings check the `Build pull requests for this project:` option. Set the `URL versioning scheme` to `Multiple versions without translations`
   6. Then, under the main `alliance-platform` settings you can add it as a subproject.
