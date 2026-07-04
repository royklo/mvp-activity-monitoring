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
# whether a URL is a feed or a regular page. Mix your own feeds with
# community aggregators, podcast feeds you appear on, or event sites
# that publish session catalogs.
sources:
  - https://yourblog.example.com/feed.xml
  - https://anchor.fm/your-podcast/rss
  - https://youtube.com/feeds/videos.xml?channel_id=XXXXXXXX
  - https://community-aggregator.example.com/feed.xml
  - https://someevent.example.com/sessions

# Keywords the workflow filters on.
#
# - For sources you author yourself (your own blog, your own YouTube),
#   leave this empty - everything you publish is by definition yours.
# - For sources you do NOT own (community aggregators, event catalogs,
#   a co-host's podcast feed), list your own name and any handles that
#   uniquely identify your content, so only items about or by you
#   become activity entries.
keywords:
  - Roy Klooster
  - royklo
  - "@royklooster"

# Auto-merge the nightly PR when no conflicts exist. Leave false if you
# want to review every entry before it lands on main.
auto_merge: false
```

The workflow does **not** apply default technology areas or a default target audience. The model picks Primary/Additional Technology Area and Target Audience from what each individual piece of content is actually about, using the full portal enum in `references/technology-areas.md`. If a source doesn't clearly map to one area, the field is written as `(uncertain - please review)` in the PR — you fill it in during review.

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

Each run that finds new content opens a **fresh PR on its own branch**, so if you skip a night the older PRs still sit there waiting. Branches look like:

```
mvp-monitor/2026-07-04-183021-blog
mvp-monitor/2026-07-05-183017-blog-event
mvp-monitor/2026-07-06-183024-podcast
```

The suffix is a slug of the activity types the run detected (`blog`, `event`, `podcast`, `webinar`, `opensource`, `mentorship`, `usergroup`, `feedback`, `support`, `product-feedback`), so at a glance you know what's in the PR.

If `auto_merge: true`, each PR merges as soon as it's mergeable. If `auto_merge: false` (the default), review the draft first — see the next section.

Merged files stay in `activities/` as your permanent log. Everything already processed is tracked in `.state/seen.json` so the next run skips it.

## Editing an activity before you merge

Every draft is written by a language model, so before it goes into your MVP portal you almost always want to tweak the wording, fill in analytics numbers, or fix a wrong Technology Area pick. Two ways:

### Option A — edit in the GitHub web UI (fastest for small tweaks)

1. Open the PR that the workflow created.
2. Click the file in `activities/` that you want to change.
3. Click the pencil icon in the top right of the file view.
4. Edit the markdown directly - fix wording, replace `(fill from analytics before submitting)` with real numbers, correct a Technology Area, add or remove a Target Audience line, change the Activity Type if the model guessed wrong.
5. **Commit directly to the PR branch** (choose "Commit directly to the `mvp-monitor/…` branch" — do not open a new PR).
6. Merge when you're happy.

### Option B — check out the branch locally (better for bigger edits or multiple files)

```bash
# grab the branch the workflow just pushed
git fetch origin
git checkout mvp-monitor/2026-07-04-183021-blog

# edit as many files as you want
code activities/2026-07-04-*.md

# push the edits back to the PR
git add activities/
git commit -m "review: polish MVP activity drafts"
git push
```

The PR updates in place. Merge when it's ready.

### What to check before you merge

- **Description and Private Description** read naturally and don't fabricate anything the source doesn't say.
- **Number of Views** (or Livestream views / On-demand views / Number of sessions / In-Person Attendees for non-blog types) is replaced with a real number if you have one, or left as the placeholder if you don't - the placeholder is a signal to yourself when you paste into the portal.
- **Primary / Additional Technology Area** points to what the content actually covers - the model uses only what's in `references/technology-areas.md`, but it can still pick the wrong sibling within a category.
- **Activity Type** matches the source (Blog vs. Podcast vs. Speaker/Presenter at …). Fix here if the auto-detect got it wrong; the type-specific fields section below it should match too.
- **Target Audience** matches who the content is for. Remove or add audience lines as needed.

Once merged, copy each section of the file into the corresponding MVP portal form field and submit.

## Adjusting the schedule

Edit `.github/workflows/monitor.yml`:

```yaml
on:
  schedule:
    - cron: "0 3 * * *"   # 03:00 UTC nightly
  workflow_dispatch:       # keep this for manual runs
```

## Adding a non-blog activity

The template defaults to `Blog`, but the model picks a different Activity Type when the source clearly matches one (a podcast RSS feed, a YouTube feed, an event page, an open-source repo). After the PR opens you can also edit the generated file and change `## Activity Type` yourself before merging.

Every Activity Type has slightly different follow-up fields. The template's **Type-specific fields** section lists them. Full reference:

- **[references/activity-types.md](references/activity-types.md)** — every Activity Type and its per-type fields (Number of sessions, Livestream views, In-Person Attendees, Microsoft Event enum, etc.).
- **[references/technology-areas.md](references/technology-areas.md)** — every Primary / Additional Technology Area value, grouped by portal category.

Supported Activity Types (verbatim as they appear in the portal):
`Blog`, `Podcast`, `Webinar/Online Training/Video/Livestream`, `Content Feedback and Editing`, `Online Support`, `Open Source/Project/Sample code/Tools`, `Product Feedback`, `Mentorship/Coaching`, `Speaker/Presenter at Microsoft Event`, `Speaker/Presenter at Third-party Event`, `User Group Owner`.

## What's in the repo

```
.github/workflows/monitor.yml   # nightly workflow
scripts/monitor.py              # single-file script
templates/activity_template.md  # MVP portal field layout
references/activity-types.md    # per-type field reference
references/technology-areas.md  # full tech area enum
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
