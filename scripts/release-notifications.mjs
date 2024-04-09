const baseUrl = 'https://github.com/AllianceSoftware/alliance-platform-py/tree/main/packages/';

function getPackageChangelogUrl(packageName, version) {
    const dirName = packageName.split('/').pop().replace('alliance-platform-', 'ap-');
    return new URL(`${dirName}/CHANGELOG.md#${version.replace(/\./g, '')}`, baseUrl).toString();
}

/**
 * This is a script that generates a Slack message with a list of packages and their versions - it is used by the
 * release.yml github workflow.
 *
 * It expects to be passed a JSON string like:
 *
 *  [{"name": "@alliancesoftware/ui", "version": "0.0.23"}]
 */
function run() {
    const packages = JSON.parse(process.argv[2]);
    const blocks = [
        {
            type: 'header',
            text: {
                type: 'plain_text',
                text: `Alliance Platform Python Release - ${new Date().toLocaleDateString('en-AU')}`,
            },
        },
        {
            type: 'section',
            text: {
                type: 'mrkdwn',
                text: packages
                    .map(({ name, version }) => {
                        const changelogUrl = getPackageChangelogUrl(name, version);
                        return `• <${changelogUrl}|Changelog> - \`${name}@${version}\``;
                    })
                    .join('\n'),
            },
        },
    ];
    console.log(JSON.stringify({ blocks }));
}

run();
