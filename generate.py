#!/usr/bin/env python3
"""Generate catalog.json from app TOML files.

Reads catalog.toml for metadata and apps/*/app.toml for each app
entry. Emits catalog.json in the openhost.catalog.v1 feed format.

Usage:
    generate.py           # Write catalog.json
    generate.py --check   # Exit non-zero if catalog.json is stale; don't write
"""

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# App names must be lowercase alphanumeric with optional interior hyphens.
# This matches OpenHost's app_name validation.
_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")

# repo_url must be a GitHub repo: https://github.com/<org>/<repo>, with an
# optional trailing ``.git`` or ``/``. This matches repo_slug's assumption.
_REPO_URL_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+(?:\.git)?/?$"
)

VALID_CATEGORIES = {
    "ai",
    "development",
    "entertainment",
    "networking",
    "privacy",
    "productivity",
    "publishing",
    "search",
    "utility",
    "data-liberation",
}


def load_toml(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def repo_slug(repo_url: str) -> str:
    """Extract the lowercased ``org/name`` slug from a repo URL, ignoring
    scheme, host, a trailing ``.git``, and trailing slashes."""
    path = re.sub(r"^[a-z]+://[^/]+/", "", repo_url.strip(), flags=re.IGNORECASE)
    path = re.sub(r"\.git$", "", path).strip("/").lower()
    return "/".join(path.split("/")[-2:])


def check_repo_public(slug: str, token: str = "") -> tuple[bool, str]:
    """Query the GitHub API for a repo's visibility. Returns (ok, message):
    ok is False only when the repo is provably missing or private. A non-empty
    message is printed — a warning when ok, the reason when not."""
    req = urllib.request.Request(f"https://api.github.com/repos/{slug}")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        if data.get("private"):
            return False, "private"
        return True, ""
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "not found or private"
        if e.code in (403, 429):
            return True, f"rate limited (HTTP {e.code}); skipped"
        if e.code >= 500:
            return True, f"server error (HTTP {e.code}); skipped"
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return True, f"unreachable: {e.reason}; skipped"
    except (OSError, json.JSONDecodeError) as e:
        return True, f"unreachable: {e}; skipped"


def check_manifest(slug: str, ref: str, token: str = "") -> tuple[bool, str]:
    """Check the repo contains an openhost.toml manifest at its root (on ref, if
    pinned). Same (ok, message) contract as check_repo_public."""
    url = f"https://api.github.com/repos/{slug}/contents/openhost.toml"
    if ref:
        url += "?ref=" + urllib.parse.quote(ref)
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True, ""
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, f"missing openhost.toml{f'@{ref}' if ref else ''}"
        if e.code in (403, 429):
            return True, f"rate limited (HTTP {e.code}); manifest not checked"
        if e.code >= 500:
            return True, f"server error (HTTP {e.code}); manifest not checked"
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return True, f"unreachable: {e.reason}; manifest not checked"
    except OSError as e:
        return True, f"unreachable: {e}; manifest not checked"


def verify_repos(feed: dict, names: list[str] | None = None) -> int:
    """Check apps' repos are public and carry an openhost.toml; with names, only
    those apps. A missing/private repo or absent manifest fails the run; a
    network/rate-limit hiccup only warns, so a transient outage never blocks."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    apps = feed["apps"]
    if names:
        wanted = set(names)
        apps = [a for a in apps if a["name"] in wanted]
        missing = sorted(wanted - {a["name"] for a in apps})
        if missing:
            print(
                f"error: no catalog app named: {', '.join(missing)}",
                file=sys.stderr,
            )
            return 1
    failures: list[str] = []
    for app in apps:
        slug = repo_slug(app["repo_url"])
        ok, message = check_repo_public(slug, token)
        if ok and not message:
            ok, message = check_manifest(slug, app["repo_ref"], token)
        line = f"  {app['name']}: {app['repo_url']} — {message}"
        if not ok:
            failures.append(line)
        elif message:
            print(f"warning:{line}", file=sys.stderr)

    if failures:
        print(
            "error: the following apps do not reference a public repo with an "
            "openhost.toml manifest:",
            file=sys.stderr,
        )
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    print(f"verified {len(apps)} repo(s)")
    return 0


def validate_score(app_toml_path: str, value) -> int:
    """Validate an openhost_integration_score value.

    Apps may omit the field; an omitted score is emitted as 0 in
    catalog.json, which downstream UIs render as "unrated". When
    the field is present, it must be an int in 1-5.

    See SCORING.md for the rubric used to assign this value.
    """
    if value is None:
        return 0
    # bool is a subclass of int in Python, so guard against it explicitly:
    # `openhost_integration_score = true` would otherwise pass as 1 and emit
    # a JSON boolean that the downstream Go consumer cannot decode as an int.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 5:
        print(
            f"error: {app_toml_path}: openhost_integration_score must be an integer 1-5, got {value!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


# Maximum length of a score explanation, in characters. The explanation is a
# single short sentence shown in the catalog UI next to the rating; this guards
# against multi-paragraph blurbs that would break the layout.
_MAX_EXPLANATION_LEN = 280


def validate_explanation(app_toml_path: str, value, score: int) -> str:
    """Validate an openhost_integration_score_explanation value.

    The explanation is the human-readable counterpart to the score: one short
    sentence describing why the app earned its rating (see SCORING.md). It is
    optional. An omitted explanation is emitted as "" in catalog.json.

    Rules:
      - Must be a string when present.
      - Must be <= _MAX_EXPLANATION_LEN characters.
      - Must be empty when the app is unrated (score == 0); an explanation
        without a score is a mistake worth catching at generate time.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        print(
            f"error: {app_toml_path}: openhost_integration_score_explanation "
            f"must be a string, got {value!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    text = value.strip()
    if score == 0 and text:
        print(
            f"error: {app_toml_path}: openhost_integration_score_explanation is set "
            "but openhost_integration_score is missing; an explanation requires a score",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(text) > _MAX_EXPLANATION_LEN:
        print(
            f"error: {app_toml_path}: openhost_integration_score_explanation must be "
            f"<= {_MAX_EXPLANATION_LEN} characters, got {len(text)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return text


def build_feed(root: str) -> dict:
    """Build the feed dict (excluding generated_at) from the source TOML files."""
    catalog_path = os.path.join(root, "catalog.toml")
    catalog = load_toml(catalog_path).get("catalog", {})

    source_id = catalog.get("source_id", "official")
    source_name = catalog.get("name", "OpenHost Official")

    apps_dir = os.path.join(root, "apps")
    apps: list[dict] = []
    category_errors: list[str] = []

    for entry in sorted(os.listdir(apps_dir)):
        app_toml = os.path.join(apps_dir, entry, "app.toml")
        if not os.path.isfile(app_toml):
            continue

        data = load_toml(app_toml)
        app = data.get("app", {})

        name = app.get("name", "")
        if not name:
            print(
                f"error: {app_toml}: missing required [app].name field",
                file=sys.stderr,
            )
            sys.exit(1)
        if not _NAME_PATTERN.match(name):
            print(
                f"error: {app_toml}: invalid [app].name {name!r}; "
                "must be lowercase alphanumeric with optional interior hyphens",
                file=sys.stderr,
            )
            sys.exit(1)
        repo_url = app.get("repo_url")
        if not repo_url:
            print(
                f"error: {app_toml}: missing required [app].repo_url field",
                file=sys.stderr,
            )
            sys.exit(1)
        if not _REPO_URL_PATTERN.match(repo_url):
            print(
                f"error: {app_toml}: invalid [app].repo_url {repo_url!r}; "
                "must be a GitHub repo URL like https://github.com/<org>/<repo>",
                file=sys.stderr,
            )
            sys.exit(1)

        score = validate_score(app_toml, app.get("openhost_integration_score"))
        explanation = validate_explanation(
            app_toml, app.get("openhost_integration_score_explanation"), score
        )

        categories = app.get("categories", [])
        invalid = [cat for cat in categories if cat not in VALID_CATEGORIES]
        if invalid:
            category_errors.append(f"  {name}: {', '.join(repr(c) for c in invalid)}")

        feed_app = {
            "name": name,
            "title": app.get("title", name),
            "description": app.get("description", ""),
            "repo_url": app["repo_url"],
            "repo_ref": app.get("repo_ref", ""),
            "icon_url": app.get("icon_url", ""),
            "tags": app.get("tags", []),
            "categories": categories,
            "website_url": app.get("website_url", ""),
            "docs_url": app.get("docs_url", ""),
            "openhost_integration_score": score,
            "openhost_integration_score_explanation": explanation,
        }

        apps.append(feed_app)

    if category_errors:
        valid_list = ", ".join(sorted(VALID_CATEGORIES))
        print(
            f"error: the following apps have invalid categories "
            f"(allowed: {valid_list}):",
            file=sys.stderr,
        )
        for line in category_errors:
            print(line, file=sys.stderr)
        sys.exit(1)

    # Each app's `name` is the identifier the catalog uses for URLs, DB keys,
    # and the default deployed app name. Within a single source, both the name
    # and the underlying repo (org/name slug) must be unique; otherwise the
    # catalog sync rejects the feed entirely.
    seen_names: dict[str, int] = {}
    seen_repos: dict[str, int] = {}
    for i, app in enumerate(apps):
        name = app["name"]
        if name in seen_names:
            first = apps[seen_names[name]]["title"]
            print(
                f"error: duplicate name {name!r} (first seen in {first!r}); "
                "each app in a source must have a unique name",
                file=sys.stderr,
            )
            sys.exit(1)
        seen_names[name] = i

        slug = repo_slug(app["repo_url"])
        if slug in seen_repos:
            first = apps[seen_repos[slug]]["title"]
            print(
                f"error: duplicate repo {slug!r} (first seen in {first!r}); "
                "each app in a source must reference a unique repository",
                file=sys.stderr,
            )
            sys.exit(1)
        seen_repos[slug] = i

    return {
        "schema": "openhost.catalog.v1",
        "source_id": source_id,
        "source_name": source_name,
        "apps": apps,
    }


def stable_copy(feed: dict) -> dict:
    """Return a copy of the feed with generated_at stripped, for comparisons."""
    return {k: v for k, v in feed.items() if k != "generated_at"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate catalog.json")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if catalog.json does not match the source TOML files. Does not write.",
    )
    parser.add_argument(
        "--verify-repos",
        action="store_true",
        help="Check apps' repos are public and carry an openhost.toml (network). Does not write.",
    )
    parser.add_argument(
        "apps",
        nargs="*",
        help="With --verify-repos, only check these app names (default: all).",
    )
    args = parser.parse_args()
    if args.apps and not args.verify_repos:
        parser.error("app names are only accepted with --verify-repos")

    root = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(root, "catalog.json")

    feed = build_feed(root)
    fresh_stable = stable_copy(feed)

    if args.verify_repos:
        return verify_repos(feed, names=args.apps or None)

    if args.check:
        try:
            with open(output_path) as f:
                committed = json.load(f)
        except FileNotFoundError:
            print(
                f"error: {output_path} does not exist. Run `python3 generate.py`.",
                file=sys.stderr,
            )
            return 1
        if stable_copy(committed) != fresh_stable:
            print(
                f"error: {output_path} is stale. Run `python3 generate.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{output_path} is up to date")
        return 0

    # Preserve catalog.json (and its generated_at) when the feed content is
    # unchanged, so no-op runs don't churn the timestamp or the git diff.
    try:
        with open(output_path) as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = None
    if existing is not None and stable_copy(existing) == fresh_stable:
        print(f"{output_path} is already up to date")
        return 0

    feed["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(output_path, "w") as f:
        json.dump(feed, f, indent=2)
        f.write("\n")
    print(f"Generated {output_path} with {len(feed['apps'])} apps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
