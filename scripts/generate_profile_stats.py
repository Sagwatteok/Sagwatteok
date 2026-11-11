"""Generate public GitHub statistics. No private repository data is published.

Counts commits authored by the profile owner in the default-branch histories
of public owned/contributed repositories. Identical commit SHAs are counted
once. Lines changed are additions + deletions, excluding merge commits.
Stars are received by owned, non-fork public repositories.
"""

import html
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request


API = "https://api.github.com/graphql"


def graphql(query, **variables):
    token = os.environ["GH_TOKEN"]
    body = json.dumps({"query": query, "variables": variables}).encode()
    for attempt in range(3):
        request = urllib.request.Request(API, data=body, headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "public-profile-statistics",
        })
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.load(response)
            if result.get("errors"):
                raise RuntimeError("GitHub GraphQL query failed: " + json.dumps(result["errors"]))
            return result["data"]
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("GitHub API retries exhausted")


def collect(login):
    profile = graphql("query($login:String!){user(login:$login){id}}", login=login)["user"]
    repositories = {}
    stars = 0
    for contributed in (False, True):
        cursor = None
        connection = (
            "repositoriesContributedTo(first:100,after:$cursor,includeUserRepositories:true,contributionTypes:[COMMIT])"
            if contributed else
            "repositories(first:100,after:$cursor,privacy:PUBLIC,ownerAffiliations:[OWNER],isFork:false)"
        )
        query = """query($login:String!,$cursor:String){user(login:$login){
          CONNECTION {nodes{nameWithOwner isPrivate isFork stargazerCount
            defaultBranchRef{name}} pageInfo{hasNextPage endCursor}}
        }}""".replace("CONNECTION", connection)
        while True:
            user = graphql(query, login=login, cursor=cursor)["user"]
            page = user["repositoriesContributedTo" if contributed else "repositories"]
            for repo in page["nodes"]:
                if repo["isPrivate"]:
                    continue
                if not contributed:
                    stars += repo["stargazerCount"]
                if repo["defaultBranchRef"]:
                    repositories[repo["nameWithOwner"]] = repo
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

    commit_query = """query($owner:String!,$name:String!,$author:ID!,$cursor:String){
      repository(owner:$owner,name:$name){defaultBranchRef{target{... on Commit{
        history(first:100,after:$cursor,author:{id:$author}){
          nodes{oid additions deletions parents(first:2){totalCount}}
          pageInfo{hasNextPage endCursor}
        }
      }}}}
    }"""
    seen = set()
    lines = 0
    active_repositories = 0
    for full_name in sorted(repositories):
        owner, name = full_name.split("/", 1)
        cursor = None
        has_commits = False
        while True:
            data = graphql(commit_query, owner=owner, name=name,
                           author=profile["id"], cursor=cursor)
            page = data["repository"]["defaultBranchRef"]["target"]["history"]
            has_commits = has_commits or bool(page["nodes"])
            for commit in page["nodes"]:
                if commit["oid"] in seen:
                    continue
                seen.add(commit["oid"])
                if commit["parents"]["totalCount"] <= 1:
                    lines += commit["additions"] + commit["deletions"]
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
        active_repositories += int(has_commits)
    return {"stars": stars, "commits": len(seen), "lines_changed": lines,
            "repositories_with_contributions": active_repositories}


def render(stats):
    rows = [
        ("star", "Stars Earned", stats["stars"]),
        ("commit", "Total Commits", stats["commits"]),
        ("code", "Lines of Code Changed", stats["lines_changed"]),
        ("repo", "Repositories with Contributions", stats["repositories_with_contributions"]),
    ]
    icons = {
        "star": '<path d="m8 1 2.1 4.3 4.7.7-3.4 3.3.8 4.7L8 11.8 3.8 14l.8-4.7L1.2 6l4.7-.7Z"/>',
        "commit": '<circle cx="8" cy="8" r="3"/><path d="M0 8h5m6 0h5"/>',
        "code": '<path d="m5 4-4 4 4 4m6-8 4 4-4 4M9.5 2l-3 12"/>',
        "repo": '<rect x="3" y="1.5" width="11" height="13" rx="1.5"/><path d="M3 11h11M6 4h5M6 7h3"/>',
    }
    fragments = []
    for i, (icon, label, value) in enumerate(rows):
        y = 78 + i * 27
        fragments.append(
            '<g transform="translate(24,{})" fill="none" stroke="#9680be" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">{}</g>'.format(y - 12, icons[icon])
            + '<text x="49" y="{}" class="label">{}</text>'.format(y, html.escape(label))
            + '<text x="370" y="{}" text-anchor="end" class="value">{:,}</text>'.format(y, value)
        )
    description = "; ".join("{}: {:,}".format(label, value) for _, label, value in rows)
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="220" viewBox="0 0 400 220" role="img" aria-labelledby="title description">
<title id="title">Eunji Kim's GitHub Statistics</title>
<desc id="description">''' + html.escape(description) + '''. Public repositories, default branches only. Lines changed exclude merges.</desc>
<style>
text{font-family:'Segoe UI',Ubuntu,Helvetica,Arial,sans-serif}
.heading{font-size:18px;font-weight:600;fill:#75628f}
.label{font-size:12px;font-weight:600;fill:#8b8b8b}
.value{font-size:13px;font-weight:600;fill:#8b8b8b}
.note{font-size:10px;fill:#8b8b8b}
@media(prefers-color-scheme:dark){.heading{fill:#c2abe3}.label,.value,.note{fill:#b6b2be}}
</style>
<rect x=".5" y=".5" width="399" height="219" rx="6" fill="none" stroke="#b4a4ce" stroke-opacity=".35"/>
<text x="24" y="37" class="heading">GitHub Statistics</text>
''' + "\n".join(fragments) + '''
<text x="24" y="202" class="note">Public repositories · Default branches · All time</text>
</svg>
'''


if __name__ == "__main__":
    owner = os.environ.get("PROFILE_OWNER", "Sagwatteok")
    data = collect(owner)
    output = Path(__file__).resolve().parents[1] / "assets" / "github-statistics.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(data), encoding="utf-8")
    print(json.dumps(data))
