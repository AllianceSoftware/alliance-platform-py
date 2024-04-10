# Changesets Integration

Some extra details about the setup to help future me (and others), particularly the use of [changesets](https://github.com/changesets/changesets)
for pypi rather than NPM.

The workflow provided by `changesets` is great; it makes tracking changes and managing releases very easy and
removes friction. It only supports NPM explicitly but provides the necessary hooks to adapt it to other usages.

This works as follows:

* We use yarn workspaces to expose to `changesets` which packages are available. See the root package.json `workspaces` entry.
* Each Python package in `packages/` has a `package.json` file that has a `name` that matches the `pyproject.toml` name, and the
  current version of the package.
* When you run `yarn changeset` it will display the available packages and versions based on this setup
* In `releases.yml`, we use `changesets/action@v1` to handle the Pull Request creation and publishing. This specifies a different
  `version` and `publish` script to use.
* Version. See `scripts/version.py`.
    * This calls `yarn changeset version`. This commands consumes all the changesets in `.changesets`, updates the package
      versions in the `packages/<package name>/package.json` files and updates the CHANGELOG.md for each package to be released.
    * The script then checks which packages need published to pypi by checking whether the current version we have listed in the `package.json`
      is available in pypi already. For these packages it generates a build and stores it in `build_artifacts`; this is purely
      so we can link to these artifacts in the Version PR to make testing the version before release easy. See the "Build packages"
      step in the `releases.yml` workflow for where these files are uploaded, and "Update PR description" for where they are linked
      to the PR.
    * That's it; after this command runs the packages have had versions bumped and changelogs updated. The `build_artifacts`
      directory will exist, but only for the Workflow (i.e. it's not committed)
* Publish. See `scripts/publish.py`.
    * This checks which packages need to be published as described above. It then runs `pdm publish` for each package. It
      will create a new tag for each published version, and importantly prints "New tag: ..." for each package. This is used
      by changesets to [detect releases](https://github.com/changesets/action/blob/c62ef9792fd0502c89479ed856efe28575010472/src/run.ts#L139).
    * After that, some extra workflows run to send notifications to slack but by this point the packages are available
      in pypi.

