# Setup

**~10 minutes. Tick as you go.**

## 1. Fork the repo

- [ ] Click **Fork** on <https://github.com/royklo/mvp-activity-monitoring> (or **Use this template** for a clean history)
- [ ] Pick **Public** or **Private**

> **Private is recommended** if you'd rather review and polish drafts before anything about your activities is publicly visible. Nothing in this tool needs to be public - everything works the same either way.
>
> Cost: public repos get unlimited Actions minutes, private repos get 2,000 min/month free (a run costs seconds).

## 2. Enable Actions permissions

`Settings → Actions → General → Workflow permissions`:

- [ ] **Read and write permissions**
- [ ] **Allow GitHub Actions to create and approve pull requests**

> Skip this and PR creation fails with 403.

## 3. (Optional) Allow auto-merge

Only if you plan to set `auto_merge: true`.

`Settings → General → Pull Requests`:

- [ ] **Allow auto-merge**

## 4. Edit `config.yml`

| Field | Set to |
|---|---|
| `sources` | Every RSS feed / page URL you want monitored |
| `keywords` | Empty for your own feeds. Your name/handles for feeds you don't own. |
| `exclude_keywords` | Substrings to drop (e.g. `sponsored`, employer name) |
| `start_date` | YYYY-MM-DD — set this so your back-catalogue doesn't flood the first PR |
| `auto_merge` | Leave `false` while you learn the drafts |
| `model` | Default `openai/gpt-4.1` — anything from the [Models catalog](https://models.github.ai/catalog/models) works |

- [ ] Commit + push (or edit in the web UI which commits directly)

> `openai/gpt-5` rejects `temperature: 0` — stick with `gpt-4.1` unless you patch `call_github_models`.

## 5. (Optional) wheremymvps.at conference sync

Only if you're a verified MVP at <https://wheremymvps.at>.

### 5a. Get a PAT

At [wheremymvps.at/api-console](https://wheremymvps.at/api-console):

- [ ] Tick `speakers:read` + `conferences:read` scopes
- [ ] Click **Create PAT** (or **Regenerate PAT**). Copy immediately — shown once.

### 5b. Add repo secret

`Settings → Secrets and variables → Actions → New repository secret`:

- [ ] Name: `WHEREMYMVPSAT_PAT`
- [ ] Value: paste the token
- [ ] **Add secret**

### 5c. Enable in `config.yml`

- [ ] `wheremymvpsat.enabled: true`
- [ ] `wheremymvpsat.user_id: <your-handle>` (from your profile URL slug, no `@`)
- [ ] Commit + push

> **Known upstream issue:** only 7 MVPs are currently visible in `/api/v1/speakers`. Enabling is safe — most users will just get zero rows until the maintainer fixes the data-population bug. See [goldjg/WhereMyMVPsAt#2](https://github.com/goldjg/WhereMyMVPsAt/issues/2).

## 6. (Optional) Custom model instructions

- [ ] Open `custom-instructions.md`
- [ ] Replace the HTML-comment block with your preferences (naming, voice, per-source rules)
- [ ] Commit + push

Leave the file comment-only to disable. Built-in guardrails always win — see the file itself for good/bad examples.

## 7. First manual run

`Actions → MVP activity monitor → Run workflow → Run workflow`:

- [ ] Wait ~30 seconds. Green tick = OK.
- [ ] Open the new PR (`mvp-monitor/YYYY-MM-DD-…`)

> **No PR?** Nothing was new. `start_date` filtered everything, everything was already in `seen.json`, or sources returned no matches. Check the run log.

## 8. Review + merge

For each file in `activities/`:

- [ ] Description reads naturally, no fabrication
- [ ] Replace `(fill from analytics before submitting)` with real numbers
- [ ] Sanity-check Primary + Additional Technology Area
- [ ] Confirm Target Audience covers every audience
- [ ] Fix Activity Type if the auto-detect got it wrong
- [ ] Merge

Merged files stay in `activities/` as your permanent log. `.state/seen.json` gets updated on the same PR so nothing gets re-added tomorrow.

## 9. Nightly cron

- [ ] Nothing — runs every 03:00 UTC. Edit the cron in `.github/workflows/monitor.yml` for a different time.

---

## Getting updates from the template

"Use this template" creates an independent copy — updates to the template repo don't auto-flow into your instance. To pull the latest fixes and features:

**One-time:** wire the template as a second git remote in your local clone.

```bash
git remote add template git@github.com:royklo/mvp-activity-monitoring.git
git fetch template
```

**When you want to update:**

```bash
git fetch template
git merge template/main
# resolve conflicts — for config.yml and custom-instructions.md, keep YOUR version
git push
```

Your config, secrets, and merged activities are safe. The template only ever changes the script, workflow, templates, and references.

> **Tip:** click **Watch → Custom → Releases** on <https://github.com/royklo/mvp-activity-monitoring> to get an email when a new version is tagged.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Run failed 403 on PR creation | You skipped step 2. Re-enable both workflow permissions. |
| Run succeeded, no PR | `has_new=false`. Check the run log — nothing new, all filtered, or all in `seen.json`. |
| `(no second area detected)` or `(uncertain - please review)` in the file | Design, not a bug. The model deliberately flagged that field for you to decide. |
| Model call HTTP 400 | `model:` value doesn't accept `temperature: 0`. Switch to `openai/gpt-4.1` or strip the temperature param in `call_github_models`. |
| wheremymvps.at returns zero rows | Wrong `user_id`, missing `speakers:read` scope, or upstream data-population gap (see `TODO.md`). |
