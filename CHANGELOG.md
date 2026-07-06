# Changelog

Notable changes to this template. Downstream instances have their own CHANGELOG - this one only tracks changes made to the template repo itself.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows semver via Conventional Commit prefixes (see `SETUP.md`).

For pre-v1.5.0 releases, see [GitHub Releases](https://github.com/royklo/mvp-activity-monitoring/releases) - the tag-on-merge workflow auto-generates release notes there from Conventional Commit messages.

## [v1.5.0] - 2026-07-06

### Added
- **Weekly auto-sync workflow.** `.github/workflows/sync-template.yml` opens a PR titled `Sync from template <version>` on downstream instances whenever the template has new commits. Path list in `.github/template-sync-paths.txt`. Guarded off on the template repo itself.
- `SYNC.md` documents what's synced, what isn't, and how to handle local customizations.
- README "Security notes" section covers prompt-injection surface via untrusted feeds, secret handling, and why `.state/seen.json` is deliberately tracked.
- SETUP troubleshooting rows for "I merged a sync PR and lost my tweak" and "config source vanished from runs".
- Malformed source entries in `config.yml` (dict without a `url:` key) now log `! ignoring malformed source entry` instead of silently disappearing.

### Changed
- `README.md` and `SETUP.md` point at the auto-sync workflow instead of the previous manual `git remote add template` + `git merge template/main` instructions.
- `call_github_models` retries up to 3 times with exponential backoff (1s, 3s, 9s) on 5xx and network errors. Nightly runs no longer drop items on a single transient blip.
- All outbound HTTP (LLM calls, fallback page fetches) now shares a single `httpx.Client()` with connection-level retries, cutting TLS handshakes per run.
- Static prompt files (drafter template, references, wrapper, wmma note, filter) are cached via `lru_cache` at first read - a 20-item run does 5 file reads instead of ~100.

### Fixed
- **Anonymized shipped examples** so downstream instances don't inherit personal identifiers via the sync workflow:
  - `README.md` semantic-filter example now uses `<your employer>` instead of a real company name.
  - `README.md` wmma config example uses `"Your-Handle"` instead of a real handle.
  - `prompts/filter.md` classifier example uses "the author's employer".
  - `custom-instructions.md` voice example is generic.
