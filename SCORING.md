# OpenHost integration score

Every app in the catalog feed carries an `openhost_integration_score`: an
integer from **1 to 5** that tells a prospective installer **how natively the
app behaves on OpenHost** — chiefly how well it adopts OpenHost single sign-on
(SSO), respects the platform's data/secret conventions, and works for both the
zone owner and any guests.

The score is **not** a measure of how good the upstream app is. A superb
project with a clunky OpenHost integration scores low; a simple app that
integrates perfectly scores high.

This document is the canonical rubric. It is referenced by both this feed repo
([app-manifest](https://github.com/imbue-openhost/app-manifest)) and the
consumer ([openhost-catalog](https://github.com/imbue-openhost/openhost-catalog)).

## What the number means

| Score | Meaning |
|-------|---------|
| **5** | Fully native. The owner is auto-logged-in with zero clicks, guests are handled correctly, and the app respects every platform convention. Nothing about being on OpenHost feels bolted-on. |
| **4** | Near-native. Owner auto-login works and platform conventions are respected, but one secondary capability is missing or imperfect (e.g. guest handling is coarse, or a public-share passthrough is absent where the app supports sharing). |
| **3** | Solid. Owner SSO works for the common path, but there are real rough edges — e.g. the owner is auto-logged-in yet invited users still need app-local accounts, or login only works on certain entry paths. |
| **2** | Minimal. The app runs and persists data correctly, but there is **no** OpenHost SSO: the owner sees the app's own login form and signs in manually. |
| **1** | Deployable only. The app starts and is reachable, but integration is rough: manual setup is required, conventions are partially violated, or the experience is noticeably degraded versus running it standalone. |
| *(omitted)* | **Unrated.** Omit the field entirely for apps that have not been scored yet. The feed emits `0`, and the catalog renders this as "—" / unrated — it does **not** mean a score of zero. |

A score of `0` is never written by hand. It only exists as the machine
representation of "unrated".

## How to score an app — the checklist

Score an app by working through the capabilities below. Start at the SSO tier
that matches the app, then adjust up or down for the secondary conventions.

### 1. SSO tier (sets the baseline)

OpenHost stamps `X-OpenHost-Is-Owner: true` on requests from an authenticated
zone owner. How completely the app consumes that signal sets the baseline
score. (See the `openhost-app` integration patterns A–E for implementations.)

- [ ] **Owner auto-login (zero clicks).** A zone owner opening the app lands
      already-signed-in as an admin/owner account. No login form, no password.
      *(Required for 4–5.)*
- [ ] **Correct guest / non-owner handling.** A visitor who is not the owner
      is either (a) bounced to the zone login, or (b) for apps with public
      sharing, served the public content without being auto-logged-in as the
      owner. *(Required for 5.)*
- [ ] **Public-page passthrough where applicable.** If the upstream app
      supports public share links (public wiki pages, shared docs, status
      pages, etc.), anonymous visitors can reach those paths without hitting
      OpenHost `/login`. *(N/A for apps with no public-sharing concept — do not
      penalize.)*
- [ ] **No manual account bootstrapping for the owner.** The owner never has
      to create an app-local account before using the app.

If owner auto-login is **absent** and the owner must use the app's own login
form, the app is capped at **2**.

### 2. Platform conventions (adjust the baseline)

- [ ] **Respects data directories.** Persists state under
      `$OPENHOST_APP_DATA_DIR` (and `$OPENHOST_APP_TEMP_DIR` for scratch);
      nothing important is written to ephemeral container paths.
- [ ] **No usable credentials left on disk.** No plaintext passwords or
      long-lived session tokens written to a path other apps (e.g.
      file-browser) can read. Prefer DB-direct session injection over writing
      a credentials file. *(A credential leak is a hard cap at 3 regardless of
      SSO quality.)*
- [ ] **No internal TLS expectations.** The app trusts the OpenHost router for
      TLS termination and does not try to manage its own certs on the routed
      port.
- [ ] **Correct host handling.** The app works behind the router's
      `X-Forwarded-Host` / `X-Forwarded-Proto` rewriting (no hard-coded
      `Host`-validation failures).
- [ ] **Clean health check.** Cold starts do not get marked "not responding"
      (a `/_healthz` 200 or placeholder during boot, where needed).

### 3. Map to a number

1. Start from the SSO tier:
   - Owner auto-login + correct guest handling + (passthrough where
     applicable) → **5**.
   - Owner auto-login but one secondary SSO capability missing → **4**.
   - Owner auto-login but invited/guest users need app-local accounts, or
     login only works on some paths → **3**.
   - No SSO; owner uses the app's native login form → **2**.
   - Barely integrated / manual setup / degraded → **1**.
2. Apply the hard caps:
   - Credential leak → cap at **3**.
   - Violates data-dir conventions in a way that loses state → cap at **2**.
3. Don't penalize for capabilities that genuinely don't apply (e.g. a stateless
   public search engine has no guest-login concept and no secrets to leak — it
   can legitimately score **5**).

## Writing the explanation

Alongside the number, every scored app should set
`openhost_integration_score_explanation`: a single short sentence, in plain
language, that tells the reader **why** the app earned its score. This is the
human-readable counterpart to the number and is shown in the catalog UI next to
the rating.

Guidelines:

- One sentence, ideally under ~160 characters.
- Describe the actual integration behavior, not the upstream app's features.
- Lead with the SSO experience, since that's what most installers care about.
- For unrated apps (no score), omit the explanation too.

Good examples:

- `"Zone owner is auto-logged in; guests are bounced to the zone login. Nothing to set up."` *(5)*
- `"Owner is auto-logged in as admin, but invited users still create app-local password accounts."` *(3)*
- `"Runs and persists data correctly, but you sign in through the app's own login form."` *(2)*
- `"Stateless public search; no accounts to manage and nothing to leak."` *(5)*

## Where the score lives

- **Source of truth:** `apps/<name>/app.toml`, fields
  `openhost_integration_score` and `openhost_integration_score_explanation`.
- **Generated feed:** `catalog.json` (built by `generate.py`); both fields are
  always present, with `0` / `""` representing "unrated".
- **Consumer:** the catalog stores and renders both fields. See the
  [openhost-catalog README](https://github.com/imbue-openhost/openhost-catalog#integration-score).
