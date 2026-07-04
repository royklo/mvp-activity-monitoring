# Setup

A one-pass checklist for standing up the workflow on your own fork. Should take about 10 minutes. Tick each item as you finish it.

## 1. Fork or template the repo

- [ ] Click **Fork** at the top of <https://github.com/royklo/mvp-activity-monitoring>, or click **Use this template** if you'd rather start with a clean commit history.
- [ ] Clone your fork locally if you want to edit configs from a shell; otherwise every file below can be edited in the GitHub web UI.

Repo can be public or private. Public gets you unlimited Actions minutes; private uses your free 2,000 min/month allowance (a nightly run costs a few seconds).

## 2. Enable Actions permissions

`Settings` -> `Actions` -> `General` -> **Workflow permissions**:

- [ ] Select **Read and write permissions**.
- [ ] Tick **Allow GitHub Actions to create and approve pull requests**.

Without this the workflow will run but the PR-creation step at the end will fail with a 403.

## 3. (Only if you set `auto_merge: true`) Allow auto-merge

`Settings` -> `General` -> scroll to **Pull Requests**:

- [ ] Tick **Allow auto-merge**.

Skip this step if you want to review every PR by hand.

## 4. Edit `config.yml`

Open `config.yml` in the web UI (or your editor) and set:

- [ ] `sources:` — every RSS feed and page URL you want monitored. Feeds are auto-detected; non-feed URLs are fetched as HTML pages. Comment out the example entries you don't need.
- [ ] `keywords:` — leave empty for sources you author yourself. For sources you don't own (community aggregators, event catalogs, a co-host's podcast), list your own name and handles so only your content passes.
- [ ] `exclude_keywords:` — case-insensitive substrings dropped before the include check. Common uses: your day-job employer's name, "sponsored", any topic that doesn't count as MVP activity.
- [ ] `start_date:` — YYYY-MM-DD lower bound. Set this before your first run so the initial PR doesn't try to backfill your entire archive.
- [ ] `auto_merge:` — leave `false` while you're getting a feel for the drafts. Flip to `true` once you trust the output.
- [ ] `model:` — default is `openai/gpt-4.1`. Any model from <https://models.github.ai/catalog/models> works. Note: `openai/gpt-5` rejects `temperature: 0` so it needs a code tweak in `call_github_models` before you can pick it here.
- [ ] Commit + push if you edited locally. If you edited in the web UI, GitHub commits directly to `main`.

## 5. (Optional) Enable Where My MVPs At? conference sync

Only do this section if you have a verified MVP account at <https://wheremymvps.at>.

### 5a. Generate a PAT with the `speakers:read` scope

- [ ] Sign in at <https://wheremymvps.at/api-console>.
- [ ] Under **PAT Management**, tick both `speakers:read` and `conferences:read` scopes.
- [ ] Click **Create PAT** (or **Regenerate PAT** if you already have one). Copy the token immediately — it's shown once.

### 5b. Store the PAT as a repo secret

- [ ] `Settings` -> `Secrets and variables` -> `Actions` -> **New repository secret**.
- [ ] Name: `WHEREMYMVPSAT_PAT`.
- [ ] Value: paste the token from step 5a.
- [ ] Click **Add secret**.

The workflow reads this secret as an environment variable at run time; it's never written to logs or the repo.

### 5c. Enable in `config.yml`

- [ ] Set `wheremymvpsat.enabled: true`.
- [ ] Set `wheremymvpsat.user_id:` to your wheremymvps.at handle (visible on your profile page URL slug — no `@` prefix, case-sensitive).
- [ ] Commit + push.

Known issue while writing this: only 7 MVPs currently appear in the `/api/v1/speakers` collection even though the UI shows many more. See `TODO.md` for the follow-up on that. Enabling the integration today is safe (returns zero records for most users), just don't expect PRs until upstream fixes the data-population bug.

## 6. (Optional) Add your own model instructions

- [ ] Open `custom-instructions.md`.
- [ ] Replace the giant HTML comment with your own preferences (naming, voice, per-source rules). Examples in the file itself and in the README section **"Customising the model's behaviour"**.
- [ ] Commit + push. Leave the file with only HTML comments to disable.

The custom-instructions block gets appended to the model prompt as a `## Custom instructions (user-provided)` section. Built-in guardrails (no fabrication, verbatim enums, no frontmatter, plain hyphens) always win in conflicts.

## 7. Trigger the first run manually

- [ ] Go to `Actions` -> `MVP activity monitor` -> **Run workflow** -> **Run workflow** button.
- [ ] Wait ~30 seconds for the run to complete. Green tick = OK.
- [ ] Open the newly created PR (branch name looks like `mvp-monitor/2026-07-05-183021-blog`).

If no PR appeared, the workflow found nothing new — either your `start_date` filtered everything out, all items were already in `.state/seen.json`, or the sources returned no matches. Check the run log under **Actions** for details.

## 8. Review and merge the first PR

For each file in `activities/`:

- [ ] Read the Description and Private Description for accuracy.
- [ ] Fill in `Number of Views` (or per-type analytics) with real numbers from your analytics tool, or leave the placeholder if you don't track that.
- [ ] Sanity-check Primary + Additional Technology Area — the model is anchored on your RSS tags, but occasionally picks a weak second area. `(no second area detected - please review)` means the model deliberately abstained; add one yourself if you disagree.
- [ ] Confirm Target Audience covers every audience the content genuinely serves.
- [ ] Fix Activity Type if the auto-detect got it wrong.
- [ ] Merge the PR.

Merged files stay in `activities/` as your permanent log. `.state/seen.json` is updated on the same PR, so tomorrow's run won't re-add anything you already merged.

## 9. Confirm the nightly schedule

- [ ] Nothing to do — the workflow now runs every day at 03:00 UTC. Adjust the cron in `.github/workflows/monitor.yml` if you want a different time.

## Troubleshooting

**Run failed with 403 on PR creation** — you skipped step 2. Go back and tick both permissions.

**Run succeeded but no PR appeared** — the `has_new` output was `false`. Either no new items, everything was filtered, or every item was already seen. Check the run log.

**PR opened but the file has `(no second area detected)` / `(uncertain - please review)`** — the model flagged that field for you to fill by hand. That's the design, not a bug.

**Model call fails with HTTP 400** — the `model:` value in `config.yml` might be one that doesn't accept `temperature: 0` (e.g. `openai/gpt-5`). Switch to `openai/gpt-4.1` or patch `call_github_models` in `scripts/monitor.py` to strip the temperature parameter.

**wheremymvps.at returns zero rows** — either your `user_id` is wrong (check the exact handle from your profile URL), the PAT is missing the `speakers:read` scope, or you're hitting the current upstream data-population gap. See `TODO.md`.
