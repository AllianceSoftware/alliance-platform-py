import core from '@actions/core';
import github from '@actions/github';

/**
 * Update the PR description to remove reference to npm and instead reference pypi.
 *
 * Adds a section with links to the build artifacts. This requires the URL to the build
 * artifacts is passed in as an argument. See release.yaml for how this happens.
 */
async function run(artifactsUrl) {
    const octokit = github.getOctokit(process.env.GITHUB_TOKEN)

    // You can also pass in additional options as a second parameter to getOctokit
    // const octokit = github.getOctokit(myToken, {userAgent: "MyActionVersion1"});
    const repoDetails = {
                owner: 'AllianceSoftware',
        repo: 'alliance-platform-py',

    }

    const { data: pullRequests } = await octokit.rest.pulls.list(repoDetails);
    const versionPr = pullRequests.find((pr) => pr.title === "Version Packages");
    if (versionPr) {
        const newBody = versionPr.body.replace('published to npm', 'published to pypi') + `
## Build Artifacts

You can download the built packages [here](${artifactsUrl}) for testing before releasing.
        `;
        await octokit.rest.pulls.update({
            ...repoDetails,
            pull_number: versionPr.number,
            body: newBody,
        })
    } else {
        console.warn("Could not find the PR with title 'Version Packages'")
    }

}
run(process.argv[process.argv.length - 1])
