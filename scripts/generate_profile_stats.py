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
    languages = {}
    for contributed in (False, True):
        cursor = None
        connection = (
            "repositoriesContributedTo(first:100,after:$cursor,includeUserRepositories:true,contributionTypes:[COMMIT])"
            if contributed else
            "repositories(first:100,after:$cursor,privacy:PUBLIC,ownerAffiliations:[OWNER],isFork:false)"
        )
        query = """query($login:String!,$cursor:String){user(login:$login){
          CONNECTION {nodes{nameWithOwner isPrivate isFork stargazerCount
            defaultBranchRef{name} languages(first:100,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}} pageInfo{hasNextPage endCursor}}
        }}""".replace("CONNECTION", connection)
        while True:
            user = graphql(query, login=login, cursor=cursor)["user"]
            page = user["repositoriesContributedTo" if contributed else "repositories"]
            for repo in page["nodes"]:
                if repo["isPrivate"]:
                    continue
                if not contributed:
                    stars += repo["stargazerCount"]
                    for edge in repo["languages"]["edges"]:
                        lang = edge["node"]["name"]
                        item = languages.setdefault(lang, {"size": 0, "color": edge["node"]["color"]})
                        item["size"] += edge["size"]
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
            "repositories_with_contributions": active_repositories, "languages": languages}


def render(stats):
    template_dir = Path(__file__).resolve().parent / "stats-templates"
    output = (template_dir / "overview.svg").read_text(encoding="utf-8")
    values = {
        "name": "Eunji Kim",
        "stars": format(stats["stars"], ","),
        "commits": format(stats["commits"], ","),
        "lines_changed": format(stats["lines_changed"], ","),
        "repos": format(stats["repositories_with_contributions"], ","),
    }
    for key, value in values.items():
        output = output.replace("{{ " + key + " }}", html.escape(value))
    return output


def render_languages(stats):
    template = (Path(__file__).resolve().parent / "stats-templates" / "languages.svg").read_text(encoding="utf-8")
    languages = sorted(stats["languages"].items(), key=lambda item: item[1]["size"], reverse=True)
    if len(languages) > 7:
        remaining = sum(item["size"] for _, item in languages[6:])
        languages = languages[:6] + [("Other", {"size": remaining, "color": "#8b8b8b"})]
    total = sum(item["size"] for _, item in languages)
    progress, legend = [], []
    for index, (name, item) in enumerate(languages):
        proportion = 100 * item["size"] / total if total else 0
        color = html.escape(item["color"] or "#8b8b8b", quote=True)
        ratio = 1 if index == len(languages) - 1 else (0.99 if proportion > 50 else 0.98)
        progress.append('<span class="progress-item" style="background-color:{};width:{:.3f}%;margin-right:{:.3f}%;"></span>'.format(color, ratio * proportion, (1 - ratio) * proportion))
        legend.append(
            '<li style="animation-delay:{}ms;">'.format(index * 150)
            + '<svg xmlns="http://www.w3.org/2000/svg" class="octicon" style="fill:{};" viewBox="0 0 16 16" width="16" height="16"><path d="M8 4a4 4 0 100 8 4 4 0 000-8z"/></svg>'.format(color)
            + '<span class="lang">{}</span><span class="percent">{:.2f}%</span></li>'.format(html.escape(name), proportion)
        )
    if not languages:
        legend.append('<li style="transform:none;"><span class="lang">No public language data yet</span></li>')
    return template.replace("{{ progress }}", "".join(progress)).replace("{{ lang_list }}", "\n".join(legend))


if __name__ == "__main__":
    owner = os.environ.get("PROFILE_OWNER", "Sagwatteok")
    data = collect(owner)
    output = Path(__file__).resolve().parents[1] / "assets" / "github-statistics.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(data), encoding="utf-8")
    (output.parent / "github-languages.svg").write_text(render_languages(data), encoding="utf-8")
    print(json.dumps(data))
