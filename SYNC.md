# Staying in sync with the template

This repo (or one you templated/forked from it) receives improvements over time from `royklo/mvp-activity-monitoring`. This document explains how updates reach your instance without touching your local config or drafted activities.

## How updates arrive

`.github/workflows/sync-template.yml` runs weekly (Monday 04:00 UTC) and also on manual trigger. On each run it:

1. Fetches `royklo/mvp-activity-monitoring`.
2. Overlays the paths listed in `.github/template-sync-paths.txt` from `template/main` onto your working tree.
3. Opens a PR titled `Sync from template <version>`. If nothing changed since your last merge, no PR is opened.

You review the diff, merge if the changes look right, or close the PR if you don't want them.

## What gets synced

The current manifest is `.github/template-sync-paths.txt`. At the time of writing:

- `scripts/` — monitor, tests, deps
- `prompts/` — LLM prompts (drafter + classifier + fragments)
- `templates/` — MVP portal activity template
- `references/` — activity types + technology areas enum
- `.github/workflows/` — nightly monitor, CI, release, and this sync workflow itself
- `.github/template-sync-paths.txt` — the manifest is itself synced, so template changes to the list reach you
- `.gitignore`
- `README.md`, `SETUP.md`, `SYNC.md`

## What is NOT synced

- `config.yml` — your feeds, filters, wmma settings
- `custom-instructions.md` — your voice preferences
- `.state/` — nightly runtime state (seen URLs)
- `activities/` — drafted MVP activities
- `LICENSE`, `CHANGELOG.md` — per-repo

## If you customized a synced file

The sync PR shows the diff. Two ways to handle:

- **Keep template + your tweak:** merge the PR, then re-apply your tweak in a follow-up commit.
- **Keep only your tweak:** close the PR. Note that the next sync PR will show the same conflict; you can either keep closing them or remove the file's path from `.github/template-sync-paths.txt` in your fork so it's skipped going forward.

## Disable the sync entirely

Delete `.github/workflows/sync-template.yml` from your fork.
