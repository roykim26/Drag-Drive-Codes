# Drag Drive Simulator Codes

A static, English-language site targeting the search query `drag drive simulator codes`. The goal is
organic Google traffic first, with AdSense considered later. It is deliberately small: a Python
generator, two JSON data files, and pre-rendered HTML.

Live: <https://drag-drive-codes.pages.dev> — the custom domain `dragdrivecodes.space` is **not bound yet**.

## Repository layout

| Path | Contents |
|---|---|
| `01-research/` | Keyword/market research that justified the site (Chinese). |
| `02-product/` | Product definition: brand and domain options, code sourcing and update rules (Chinese). |
| `03-design/` | UI design notes, including the inline SVG logo (Chinese). |
| `04-site/` | The actual site: data, generator, scripts, build output. |
| `05-launch/` | Launch runbooks: Cloudflare Pages checklist, daily patrol deployment on ECS (Chinese). |

Inside `04-site/`:

| Path | Purpose |
|---|---|
| `data/codes.json` | Single source of truth for every code, reward, source and date. |
| `data/site.json` | Site-wide config: brand, base URL, contact email, last-checked date, ads switch. |
| `build.py` | The generator. Standard library only. |
| `dist/` | Deployable build: directory-style URLs, root-absolute links, `_headers`, `_redirects`. Not committed. |
| `dist-local/` | Flat `.html` files with relative links, for double-click preview only. Not committed. |
| `scripts/` | `patrol.py` (daily upstream check) and `gsc_submit.py` (optional Search Console helper). |

## Build

```bash
cd 04-site
python build.py
```

`build.py` reads `data/codes.json` and `data/site.json` and writes both `dist/` and `dist-local/`.
No third-party packages are required (Python 3.10+).

The build refuses to publish on bad input and points at the offending field:

- **Data**: empty or lowercase codes; the same code in two buckets; active/reported entries with no
  source; `confirmed` with fewer than two distinct sources; non-positive `reward_min`;
  `reward_max < reward_min`; `last_verified` or `in_game_verified` in the future; `in_game_verified`
  on anything that is not `confirmed`; an active entry carrying `expired_on`; status contradicting the
  list the entry sits in; a zero RP total while active codes exist.
- **Copy**: stale number words such as "nine codes are confirmed" after the active count changes.
- **Ads**: if `ads.enabled` is true, `ads.client` must match `ca-pub-` + 16 digits and every slot must
  be non-empty digits.

A failed build exits non-zero before touching `dist/`, so the last good output stays in place.

## Deploy

Cloudflare Pages project `drag-drive-codes`, direct upload (no Git integration):

```bash
cd 04-site
npx wrangler pages deploy dist --project-name drag-drive-codes
```

`dist/` is the only deployable directory. `dist-local/` must never be uploaded. The browser-based
`wrangler login` is a manual step and is not automated anywhere in this repository.

## Daily patrol

`04-site/scripts/patrol.py` fetches the public Roblox games API for the game's universe, stores a
dated snapshot, diffs `updated` and `description` against the previous run, and extracts candidate
codes with a regex. It only prints a "needs human confirmation" list — it never edits
`data/codes.json` or any page.

```bash
python scripts/patrol.py --dry-run     # print what would happen, write nothing, notify nobody
python scripts/patrol.py               # write snapshot + report, optional webhook
```

Exit codes: `0` nothing to review, `10` candidates found, `30` fetch failed after retries,
`40` no successful run for over 36 hours. `--exit-zero` collapses them for systemd. The webhook URL
is read from `DDC_WEBHOOK_URL` only; it is never stored in the repo.

## Code rules and ad switch

- **Confirmed** — two independent sources, both recorded in `sources`.
- **Reported** — a single source; shown separately, never counted as confirmed.
- **Expired** — moved to the archive under the year it expired.
- `in_game_verified` is the date the code was last entered in-game; it is a bonus annotation on a
  confirmed code, not a third status, and must not be later than `last_verified`.
- Ads are configured in `data/site.json` under `ads` (`enabled`, `client`, `slots`). When disabled —
  the current state — the build emits no ad container, no AdSense script and no reserved height.
- AdSense is **not** integrated: there is no publisher ID anywhere in the repository.

## Not here

- No backend, no database, no server-side rendering.
- No forms: the contact page uses a `mailto:` link.
- No analytics, tag manager, pixels or cookie banner.
- No CMP for EEA/UK/Switzerland consent, which AdSense would require before ads go live.
- No CI, tests or linting pipeline; verification is the build's own checks plus manual browser passes.

Docs under `01`–`05` are written in Chinese; site copy, code and comments are English.
