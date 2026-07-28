# openhost-apps

The official OpenHost app catalog feed. Consumed by [`openhost-catalog`](https://github.com/imbue-openhost/openhost-catalog) to populate its app listing.

This repo is data-only. The Go/Python code that reads this feed lives elsewhere.

## Structure

```
catalog.toml          # Catalog-level metadata (source name)
catalog.json          # Generated feed (what consumers fetch)
generate.py           # Builds catalog.json from the TOML sources
apps/<name>/app.toml  # One directory per app
```

## Feed format

The feed follows the `openhost.catalog.v1` schema. Each app entry has:

| Field          | Required | Description |
|----------------|----------|-------------|
| `name`         | yes      | The name the app deploys as. Must be lowercase alphanumeric with optional interior hyphens. Drop any `openhost-` prefix. |
| `title`        | yes      | Display name |
| `description`  | yes      | One-line summary |
| `repo_url`     | yes      | GitHub repo containing the app's `openhost.toml` manifest |
| `repo_ref`     | no       | Pin to a branch, tag, or commit (default: repo's default branch) |
| `icon_url`     | no       | URL to an icon image |
| `tags`         | no       | Array of search tags |
| `categories`   | no       | Array of categories |
| `website_url`  | no       | Upstream project homepage |
| `docs_url`     | no       | Documentation link |
| `openhost_integration_score` | no | Integer 1-5 rating how natively the app integrates with OpenHost (SSO, data conventions, guest handling). Omit for unrated apps. See [SCORING.md](SCORING.md). |
| `openhost_integration_score_explanation` | no | One short sentence explaining *why* the app earned its score, shown in the catalog UI. Omit when unrated. See [SCORING.md](SCORING.md). |

The `name` field is the app's identifier in the catalog: it is used in catalog URLs, pre-filled as the default deployed app name when installing, and must be unique within a source.

## Integration score

Each app may carry an `openhost_integration_score` (1-5) plus a one-sentence
`openhost_integration_score_explanation`. The score rates how natively the app
behaves on OpenHost — primarily SSO quality, data/secret conventions, and guest
handling — **not** how good the upstream project is.

The full rubric and the checklist for scoring an app live in **[SCORING.md](SCORING.md)**.

`generate.py` validates both fields: the score must be an integer 1-5 when
present (omitted → `0` = unrated), and the explanation must be a short string
and may only be set when a score is set.

## Uniqueness

- **Within a source**: every app must have a unique `name` and a unique `repo_url`. Duplicates cause `generate.py` to fail.
- **Across sources**: the same name can appear in multiple source feeds without conflict. They show as separate entries in the catalog.

## Adding an app

Edit `apps/<name>/app.toml` and CI regenerates `catalog.json`.

1. Add or edit `apps/<short-name>/app.toml` with the fields above (local checkout or catalog's add app autofill).
2. Open a pull request.
3. CI runs `generate.py`, which validates the TOML and regenerates
   `catalog.json`:
   - **Branch in this repo:** the fresh `catalog.json` is committed back onto
     your PR branch automatically.
   - **Fork:** CI can't push to your fork, so it only validates; `catalog.json`
     is regenerated on `main` when the PR merges.

   If the TOML is invalid (bad name, unknown category, malformed score) the
   check fails with the reason.

If you do have a local checkout, you can regenerate ahead of CI with
`python3 generate.py` and commit `catalog.json` yourself — optional, not
required.

## Development

### Regenerate the feed

```bash
python3 generate.py
```

### Check the feed is up to date

```bash
python3 generate.py --check
```

Exits non-zero if `catalog.json` is stale relative to the TOML sources. Used by
the pre-commit hook; CI regenerates instead of checking (see below).

### Pre-commit hook

Install [pre-commit](https://pre-commit.com/) and run:

```bash
pre-commit install
```

This installs a hook that runs `generate.py --check` before each commit and
blocks stale `catalog.json` from being committed, so a local checkout stays in
sync without waiting for CI.

### CI

The `Catalog` workflow runs `generate.py` on every PR and on pushes to `main`.
It validates the TOML and regenerates `catalog.json` — committing it back to the
PR branch (same-repo) or to `main` on merge (forks) — so contributors never have
to run the generator by hand.
