# MVP Activity Monitoring

**A GitHub Actions workflow that watches your blog, podcast, RSS feed, or any URL you care about and drafts Microsoft MVP program activity entries for you every night — as pull requests.**

Built for Microsoft MVPs. Every MVP already has the GitHub features this needs (Actions minutes on public repos, GitHub Models inference). Fork it, point it at your content, and stop retyping the same portal fields.

## What it does

1. Runs on a nightly cron (03:00 UTC by default).
2. Reads your `config.yml`: a list of URLs / RSS feeds and a list of keywords.
3. Fetches each source, filters by keyword, skips anything already processed.
4. For every new match, asks a language model (via GitHub Models) to draft a copy-paste-ready MVP portal entry using a fixed markdown template.
5. Opens a pull request with the new file(s) in `activities/`.
6. Optionally auto-merges the PR (opt-in via `auto_merge: true`), otherwise you review and merge by hand.

The generated markdown mirrors the MVP portal form 1:1 — Activity Type, Primary/Additional Technology Area, Title, Description, Private Description, Target Audience, Published Date, Role, Number of Views, Quantity, Activity URL. You paste each section into the corresponding portal field. Done in under a minute per activity.

## Setup (5 minutes)

### 1. Fork or copy this repository

Fork the repo to your own GitHub account (or click **Use this template**). Public or private, both work.

### 2. Edit `config.yml`

```yaml
# Sources: any RSS feed URL or plain page URL. The workflow auto-detects
# whether a URL is a feed or a regular page.
sources:
  - https://yourblog.example.com/feed.xml
  - https://anchor.fm/your-podcast/rss
  - https://youtube.com/feeds/videos.xml?channel_id=XXXXXXXX
  - https://someevent.example.com/your-session

# Keywords: only items whose title or summary contains at least one of
# these (case-insensitive) become MVP activity entries. Leave empty to
# capture everything.
keywords:
  - intune
  - entra
  - microsoft graph

# Default technology areas — used when the model can't confidently pick
# one from the content itself.
defaults:
  primary_technology_area: Microsoft Intune
  additional_technology_areas: Microsoft Graph
  target_audience:
    - IT Pro

# Auto-merge the nightly PR when no conflicts exist. Set to false if you
# want to review every entry before it lands on main.
auto_merge: false
```

### 3. Enable the two GitHub features the workflow needs

Both are free.

**A. Workflow permissions**
`Settings` → `Actions` → `General` → **Workflow permissions**:
- Select **Read and write permissions**.
- Tick **Allow GitHub Actions to create and approve pull requests**.

**B. Auto-merge (only if you set `auto_merge: true`)**
`Settings` → `General` → scroll to **Pull Requests** → tick **Allow auto-merge**.

That's the entire setup. The nightly workflow runs at 03:00 UTC on the default schedule; trigger it manually the first time via `Actions` → `MVP activity monitor` → `Run workflow` to confirm it works.

## How the PR review flow works

After a run finds new content:

- A branch called `mvp-monitor/nightly` is created (or updated).
- A PR is opened against `main` with one markdown file per activity in `activities/`.
- If `auto_merge: true`, the PR merges as soon as it's mergeable.
- If `auto_merge: false`, review the draft, tweak the wording, fill in `Number of Views` from your analytics, and merge.

Merged files stay in `activities/` as your log. Everything already processed is tracked in `.state/seen.json` so the next run skips it.

## Adjusting the schedule

Edit `.github/workflows/monitor.yml`:

```yaml
on:
  schedule:
    - cron: "0 3 * * *"   # 03:00 UTC nightly
  workflow_dispatch:       # keep this for manual runs
```

## Adding a non-blog activity

The template defaults to `Blog`. For a podcast, webinar, or event you attended, either:
- Add the source URL and let the model detect the type from the page content, or
- After the PR opens, edit the generated file and change `## Activity Type` before you merge.

Supported values per the MVP program:
`Blog`, `Podcast`, `Webinar/online training`, `Content Feedback and Editing`, `Online support`, `OpenSource`, `Project`, `Sample Code`, `Tools`.

## What's in the repo

```
.github/workflows/monitor.yml   # nightly workflow
scripts/monitor.py              # single-file script, ~150 lines
templates/activity_template.md  # exact MVP portal field layout
config.yml                      # your sources, keywords, defaults
activities/                     # generated MD files (your log)
.state/seen.json                # dedup state, committed by the workflow
```

## Cost

Zero, if your repo is public. GitHub Actions minutes on public repos are unlimited; GitHub Models inference is free within the per-day quota (plenty for one nightly run).

Private repo? You get 2,000 free Actions minutes/month on the Free plan; a nightly run costs seconds.

## FAQ

**Do I need an OpenAI or Anthropic key?**
No. GitHub Models exposes several models (including GPT-4o) for free from inside Actions. If you'd rather use your own key, edit `scripts/monitor.py` and swap the `call_github_models` function.

**What if my blog doesn't have an RSS feed?**
Add the plain URL. The script falls back to fetching the page and pulling the `<title>` + `<meta name="description">`. Less accurate than a feed, but works.

**Can I run this outside of GitHub?**
Yes — `python scripts/monitor.py` runs anywhere, provided you set `GITHUB_TOKEN` (or swap the LLM call for another provider). GitHub Actions is just the convenient cron host.

**Will it re-add activities I already logged manually?**
No. Anything whose URL appears in `.state/seen.json` is skipped. The state file is committed as part of each PR, so once you merge, that URL is off the list.

## License

MIT. Do whatever you want with it. If you improve it, a PR is welcome but not required.
