# Changelog

Notable changes to this template. Downstream instances have their own CHANGELOG - this one only tracks changes made to the template repo itself.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows semver via Conventional Commit prefixes (see `SETUP.md`).

## [v1.0.0] - 2026-07-06

First stable release. The template is production-ready:

- **Nightly RSS + wheremymvps.at gather** with semantic LLM classifier (`prompts/filter.md`).
- **Drafter prompt split into 18 small files** under `prompts/drafter/`, plus reference files, a custom-instructions wrapper, and a wmma source note. Assembled via `string.Template.safe_substitute`.
- **Weekly sync workflow** (`.github/workflows/sync-template.yml`) opens a `Sync from template <version>` PR into every downstream instance whenever the template moves. Path manifest at `.github/template-sync-paths.txt`.
- **Auto-releases** on merge via `.github/workflows/release.yml` (tag + GitHub Release).
- **Resilient LLM calls**: 3-attempt exponential-backoff retry, shared `httpx.Client` with transport-level connection retries, static prompt files cached with `lru_cache`.
- **Guarded diagnostics**: no silent empty-response branches; malformed sources, missing PAT, and wrong wmma userId all log clear stderr lines.
- **Assert-based tests** (`scripts/test_monitor.py`) run in CI on every PR (required status check).

For the improvement history leading up to this release, see the closed PRs on this repo.
