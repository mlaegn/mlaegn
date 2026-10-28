"""Regenerate the generated parts of the profile README from GitHub itself.

- The languages line: the languages of the repos I committed to in the last year, one
  vote per repo, so a personal project counts as much as a large work repo.
- The stats card: commits, pull requests and repositories over the same year, public only.

GitHub's language bars are not used: they leave out SQL entirely and count generated
HTML, so a repo's files are read instead. Private repos count towards the languages
line when the token can see them; only language names are published, never repo names.

Usage:  GITHUB_TOKEN=... python scripts/profile.py [--dry-run]
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = "mlaegn"
ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

MIN_COMMITS = 10   # a repo with fewer of my commits says nothing about what I write
TOP = 6            # how many languages the line shows

# A language counts for a repo when one of its files is there (a path ending, any
# depth), at least `min_files` times. Order breaks ties.
RULES = [
    ("Python",     {"files": ["pyproject.toml", "requirements.txt", "setup.py"]}),
    ("SQL",        {"files": [".sql"], "min_files": 10}),
    ("Rust",       {"files": ["Cargo.toml"]}),
    ("Go",         {"files": ["go.mod"]}),
    ("TypeScript", {"files": ["tsconfig.json"]}),
    ("JavaScript", {"files": ["package.json"], "unless": "TypeScript"}),
]


def api(url, body=None):
    req = urllib.request.Request(
        url if url.startswith("https://") else "https://api.github.com" + url,
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "Accept": "application/vnd.github+json",
            "User-Agent": USER + "-profile-readme",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def contributions():
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalPullRequestContributions
          commitContributionsByRepository(maxRepositories: 100) {
            contributions { totalCount }
            repository { nameWithOwner isPrivate isFork defaultBranchRef { name } }
          }
        }
      }
    }"""
    data = api("/graphql", {"query": query, "variables": {"login": USER}})
    if "errors" in data:
        sys.exit("GraphQL: " + json.dumps(data["errors"]))
    return data["data"]["user"]["contributionsCollection"]


def private_repos(since):
    """My own private repos and my commits in each. GitHub's contribution data hides
    these, so they are counted from the commit list. Needs a token that can see them;
    the workflow token cannot, and then there are none."""
    try:
        repos = api("/user/repos?affiliation=owner&visibility=private&per_page=100")
    except urllib.error.HTTPError:
        return []
    out = []
    for r in repos:
        if r["fork"] or r["pushed_at"] < since:
            continue
        commits, page = 0, 1
        while True:
            batch = api(f"/repos/{r['full_name']}/commits?author={USER}&since={since}"
                        f"&per_page=100&page={page}")
            commits += len(batch)
            if len(batch) < 100:
                break
            page += 1
        out.append((r["full_name"], commits, r["default_branch"]))
    return out


def detect(repo, branch):
    """The languages in one repo, by RULES."""
    tree = api(f"/repos/{repo}/git/trees/{branch}?recursive=1")["tree"]
    paths = [t["path"] for t in tree if t["type"] == "blob" and "node_modules/" not in t["path"]]
    found = set()
    for lang, rule in RULES:
        hits = sum(1 for p in paths if p.endswith(tuple(rule["files"])))
        if hits >= rule.get("min_files", 1):
            found.add(lang)
    for lang, rule in RULES:
        if rule.get("unless") in found:
            found.discard(lang)
    return found


def languages(repos):
    order = [lang for lang, _ in RULES]
    votes, commits = {}, {}
    for name, n, branch, private in repos:
        found = detect(name, branch)
        label = "(private)" if private else name
        print(f"  {n:>4}  {label}: {', '.join(sorted(found, key=order.index))}")
        for lang in found:
            votes[lang] = votes.get(lang, 0) + 1
            commits[lang] = commits.get(lang, 0) + n
    ranked = sorted(votes, key=lambda l: (-votes[l], -commits[l], order.index(l)))
    return ranked[:TOP]


def card(commits, prs, repos, ink, label):
    """A three-number stats card in the README's palette."""
    cells = [(commits, "commits"), (prs, "pull requests"), (repos, "repositories")]
    font = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="96" viewBox="0 0 480 96" '
           f'font-family="{font}" text-anchor="middle">']
    for i, (n, what) in enumerate(cells):
        x = 80 + i * 160
        out.append(f'<text x="{x}" y="44" font-size="30" font-weight="600" fill="{ink}">{n:,}</text>')
        out.append(f'<text x="{x}" y="68" font-size="12" fill="{label}">{what}</text>')
    out.append(f'<text x="240" y="90" font-size="10" fill="{label}" opacity="0.7">last 12 months, public</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def replace(text, marker, body):
    pattern = re.compile(rf"(<!-- {marker}:start -->).*?(<!-- {marker}:end -->)", re.S)
    if not pattern.search(text):
        sys.exit(f"README has no <!-- {marker}:start --> / <!-- {marker}:end --> markers")
    return pattern.sub(lambda m: m.group(1) + body + m.group(2), text)


def main():
    dry = "--dry-run" in sys.argv
    since = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    c = contributions()
    by_repo = c["commitContributionsByRepository"]

    repos = [
        (r["repository"]["nameWithOwner"], r["contributions"]["totalCount"],
         r["repository"]["defaultBranchRef"]["name"], r["repository"]["isPrivate"])
        for r in by_repo if not r["repository"]["isFork"]
    ]
    seen = {name for name, *_ in repos}
    repos += [(n, k, b, True) for n, k, b in private_repos(since) if n not in seen]
    repos = [r for r in repos if r[1] >= MIN_COMMITS]

    print(f"{len(repos)} repos with {MIN_COMMITS}+ of my commits:")
    line = "<samp>" + " · ".join(languages(repos)) + "</samp>"
    print("languages:", line)

    public = [r for r in by_repo if not r["repository"]["isPrivate"]]
    commits = sum(r["contributions"]["totalCount"] for r in public)
    prs = c["totalPullRequestContributions"]
    print(f"stats: {commits} commits, {prs} PRs, {len(public)} repos")
    if dry:
        return

    text = README.read_text()
    README.write_text(replace(text, "languages", "\n  " + line + "\n  "))
    (ROOT / "img").mkdir(exist_ok=True)
    (ROOT / "img/stats-dark.svg").write_text(card(commits, prs, len(public), "#6FB8E6", "#8B9BB0"))
    (ROOT / "img/stats-light.svg").write_text(card(commits, prs, len(public), "#1F6FA8", "#57606A"))


if __name__ == "__main__":
    main()
