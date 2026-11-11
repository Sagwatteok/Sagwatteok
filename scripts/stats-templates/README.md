# GitHub Stats Transparent templates

SVG templates from [kyu0918/github-stats-transparent](https://github.com/kyu0918/github-stats-transparent), based on [rahul-jha98/github-stats-transparent](https://github.com/rahul-jha98/github-stats-transparent) and [jstrieb/github-stats](https://github.com/jstrieb/github-stats). Licensed under GPL-3.0; see LICENSE in this directory.

Modifications: overview rows reduced to Total Commits, Lines of Code Changed, and Repositories with Contributions; animation delays adjusted; card headings changed to the profile's lavender theme. The local generator fills these templates using accessible GitHub data (private repositories only when a read token is configured). Total Commits counts authored commits, rather than the upstream all-contribution counter. Languages aggregate bytes in owned non-fork repositories accessible to the configured token. Merge commits count as commits but are excluded from changed-line totals. Identical commit SHAs are counted once.

## Private repository statistics

By default, only public repositories are counted. To include private repositories, add a repository Actions secret named `PROFILE_STATS_TOKEN` containing a fine-grained personal access token owned by Sagwatteok, with Contents: read access to the repositories to include. The workflow uses this token only to read statistics; commits to the profile still use the repository-scoped GITHUB_TOKEN. Names, source code and commit details from private repositories are never written to generated SVGs. Only aggregate counts and language proportions are published. A token can include only repositories it is authorized to read.
