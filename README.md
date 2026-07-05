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

## Stay in sync with template updates

"Use this template" creates an independent copy — updates to this template don't auto-flow into your instance. To hear about new versions:

- **⭐ Star** the template repo — bookmark, appears in your Stars list. Doesn't send notifications.
- **👁 Watch → Custom → Releases** — this is the one that sends you an email whenever a new version is tagged (every merge to main on the template repo publishes a release). Recommended.

When you want to pull a template update into your instance, see the **"Getting updates from the template"** section in [SETUP.md](SETUP.md).

---

## Setup

**Full step-by-step checklist:** **[SETUP.md](SETUP.md)** — fork, permissions, config, PAT secret, first run.

> **Public or private repo?** Either works, same features. Private is recommended if you'd rather review and polish drafts before anything about your activities is publicly visible.

Quick summary of the three things you'll actually edit:

### `config.yml` — sources and filters

Filters can be global (apply to every source) or **per-source** (override on a specific feed). Bare URL strings inherit global filters; dict-shape sources can carry their own `keywords` / `exclude_keywords`:

```yaml
sources:
  # Bare URL = inherits global filters below
  - https://yourblog.example.com/feed.xml

  # Dict form = per-source semantic topic hints
  - url: https://community-aggregator.example.com/feed.xml
    keywords:
      - Intune
      - Microsoft Graph
      - Entra ID
    exclude_keywords:
      - Power BI
  - url: https://anchor.fm/some-podcast/rss
    keywords:
      - macOS management
    exclude_keywords: []

# Global filters — used only for bare URL sources above.
keywords:                # leave empty when every bare source is on-topic
exclude_keywords:
  - sponsored content

start_date: 2026-07-01   # optional: skip your back-catalogue
auto_merge: false
```

| Field | What it does |
|---|---|
| `sources` | Feeds or URLs. Bare string = uses global filters. Dict with `url:` = can override `keywords` / `exclude_keywords` for that source only. |
| `keywords` (global/per-source) | **Semantic** topic hints. A language model reads each post and asks: "is this primarily on one of these topics?" Empty = accept anything. |
| `exclude_keywords` (global/per-source) | **Semantic** exclusion. A post is dropped only when its primary topic matches — passing mentions of the excluded term in an intro or bio do NOT trigger exclusion. |
| `start_date` | YYYY-MM-DD lower bound on publish date. |
| `auto_merge` | Auto-merge nightly PRs if they're mergeable. |

**Why semantic and not substring:** a post titled *"macOS LAPS vs. Intune Compliance Policy"* whose intro says *"I work at Inforcer"* should be logged as an Intune activity, not dropped because "Inforcer" appears once. The classifier reads the whole post plus tags and decides on topic, not on string presence. Costs one extra small model call per RSS item — negligible on GH Models free tier.

**When per-source overrides are useful:** your own blog and a community aggregator can have completely different include/exclude lists.

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
