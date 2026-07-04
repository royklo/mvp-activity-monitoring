# MVP Activity Monitoring

> **A nightly GitHub Actions workflow that turns your blog posts, podcasts, videos, and conference attendances into copy-paste-ready Microsoft MVP program activity entries — as pull requests.**

Fork it, point it at your content, stop retyping portal fields.

---

## What it does

- Runs nightly (03:00 UTC by default)
- Reads `config.yml` for the sources and filters you set
- Fetches each source, skips anything it's already processed
- For every new item, asks a language model (via GitHub Models) to draft an MVP portal entry
- Opens a PR with the new file(s) in `activities/`
- You review, tweak, merge — then paste each field into the MVP portal

The generated markdown mirrors the MVP portal form 1:1: Activity Type, Primary/Additional Technology Area, Title, Description, Private Description, Target Audience, Published Date, Role, Number of Views, Quantity, Activity URL.

> **Auto-upload (roadmap):** Microsoft has not yet released a public API for the MVP contribution portal, so activities still have to be pasted in by hand — this tool drafts the fields for you. **When Microsoft ships that API, this workflow will be updated to submit merged activities directly to the portal**, and the "copy-paste each field" step goes away. Until then, the merged markdown files in `activities/` are your handoff artefact.

---

## Setup

**Full step-by-step checklist:** **[SETUP.md](SETUP.md)** — fork, permissions, config, PAT secret, first run.

Quick summary of the three things you'll actually edit:

### `config.yml` — sources and filters

```yaml
sources:
  - https://yourblog.example.com/feed.xml
  - https://anchor.fm/your-podcast/rss
  - https://youtube.com/feeds/videos.xml?channel_id=XXXXXXXX

keywords:            # leave empty for your own feeds
  - Roy Klooster     # your name/handles for feeds you don't own

exclude_keywords:    # optional
  - sponsored

start_date: 2026-07-01   # optional: skip your back-catalogue

auto_merge: false
```

| Field | What it does |
|---|---|
| `sources` | Feeds or plain URLs to monitor. Feeds auto-detected. |
| `keywords` | Include filter. Empty = accept all. Set for feeds you don't own. |
| `exclude_keywords` | Case-insensitive drop list. Applied before include. |
| `start_date` | YYYY-MM-DD lower bound on publish date. |
| `auto_merge` | Auto-merge nightly PRs if they're mergeable. |

Technology Area and Target Audience are **not** in config — the model picks them per item from what the content actually is. If it can't decide, it writes `(uncertain - please review)` and you fill it in.

### `custom-instructions.md` — your voice and preferences

Optional. If the file has any content outside HTML comments, it's appended to the model prompt as user hints.

**Good uses:**
```md
- Prefer "Microsoft Entra ID" over "Azure AD".
- My blog voice is direct - avoid "This blog post explores..." openings.
- Don't mention my employer by name in Description or Private Description.
```

**Bad uses** (fight the guardrails, produce broken output):
```md
- Fill Additional Technology Areas with "Microsoft 365" by default.
- Add a YAML frontmatter block to every file.
```

Built-in rules always win in conflicts. Reset to comment-only to disable.

### GitHub secret (optional, for wheremymvps.at)

Only if you want conference-attendance sync:

1. At [wheremymvps.at/api-console](https://wheremymvps.at/api-console) — regenerate PAT with `speakers:read` scope
2. Repo → `Settings → Secrets and variables → Actions → New repository secret` → name `WHEREMYMVPSAT_PAT`, paste token
3. In `config.yml`:
   ```yaml
   wheremymvpsat:
     enabled: true
     user_id: royklo   # your wheremymvps.at handle
   ```

---

## How the PR review flow works

Each run opens a **fresh PR on its own branch**:

```
mvp-monitor/2026-07-04-183021-blog
mvp-monitor/2026-07-05-183017-blog-event
mvp-monitor/2026-07-06-183024-podcast
```

- Branch suffix is the Activity Types found in that run (`blog`, `event`, `podcast`, `webinar`, `opensource`, ...)
- Skipped nights don't overwrite older PRs — they queue up
- `auto_merge: true` → merges when green; otherwise you review

Merged files land in `activities/` as your permanent log. Everything already merged is tracked in `.state/seen.json`.

---

## Editing an activity before you merge

Two ways.

**Web UI (fastest):**
1. Open the PR
2. Click the file → pencil icon → edit inline
3. Commit directly to the `mvp-monitor/…` branch
4. Merge

**Local (better for bigger edits):**
```bash
git fetch origin
git checkout mvp-monitor/2026-07-04-183021-blog
# edit activities/*.md
git commit -am "review: polish drafts"
git push
```

**Before you merge — check:**

- [ ] Description doesn't fabricate anything
- [ ] `Number of Views` / views / attendees replaced with real numbers (or leave the placeholder as a to-do)
- [ ] Primary + Additional Technology Area actually match the content
- [ ] Activity Type matches the source (Blog vs Podcast vs Speaker…)
- [ ] Target Audience covers every audience the content serves

Once merged, paste each `## Section` into its portal field.

---

## Adding a non-blog activity

The model picks a different Activity Type automatically when the source clearly matches — podcast RSS, YouTube feed, event page, open-source repo. If it guesses wrong, fix it in the PR before merging.

**Supported Activity Types** (verbatim from the portal):

`Blog`, `Podcast`, `Webinar/Online Training/Video/Livestream`, `Content Feedback and Editing`, `Online Support`, `Open Source/Project/Sample code/Tools`, `Product Feedback`, `Mentorship/Coaching`, `Speaker/Presenter at Microsoft Event`, `Speaker/Presenter at Third-party Event`, `User Group Owner`.

**References** (used by the model and safe to browse):

- [`references/activity-types.md`](references/activity-types.md) — per-type extra fields (Livestream views, In-Person Attendees, Microsoft Event enum, etc.)
- [`references/technology-areas.md`](references/technology-areas.md) — full Primary/Additional Technology Area enum

---

## License

MIT. Do whatever you want with it. PRs welcome, not required.
