# Changelog

Notable changes to this template. Downstream instances have their own CHANGELOG - this one only tracks changes made to the template repo itself.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows semver via Conventional Commit prefixes (see `SETUP.md`).

For pre-v1.5.0 releases, see [GitHub Releases](https://github.com/royklo/mvp-activity-monitoring/releases) - the tag-on-merge workflow auto-generates release notes there from Conventional Commit messages.

## [Unreleased]

### Added
- **Weekly auto-sync workflow.** `.github/workflows/sync-template.yml` opens a PR titled `Sync from template <version>` on downstream instances whenever the template has new commits. Path list in `.github/template-sync-paths.txt`. Guarded off on the template repo itself.
- `SYNC.md` documents what's synced, what isn't, and how to handle local customizations.

### Changed
- `README.md` and `SETUP.md` point at the auto-sync workflow instead of the previous manual `git remote add template` + `git merge template/main` instructions.

### Fixed
- **Anonymized shipped examples** so downstream instances don't inherit personal identifiers via the sync workflow:
  - `README.md` semantic-filter example now uses `<your employer>` instead of a real company name.
  - `README.md` wmma config example uses `"Your-Handle"` instead of a real handle.
  - `prompts/filter.md` classifier example uses "the author's employer".
  - `custom-instructions.md` voice example is generic.
