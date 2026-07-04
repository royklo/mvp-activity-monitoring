# TODO

Pending items that live outside a single commit.

## wheremymvps.at integration - waiting on upstream

Code is shipped and correct (`gather_wheremymvpsat` in `scripts/monitor.py`, config block in `config.yml`, secret pass-through in the workflow). Two upstream gaps block turning it on:

- **Data population gap.** `GET /api/v1/speakers` returns 23 records for 7 users. `royklo`, `Lewis-Barry`, `andrew-s-taylor` all return `count: 0` even though the UI shows their attendances. Filtering by `conferenceId` returns the same restricted set, so it's not a query-shape issue. Waiting on the maintainer's backfill or opt-in mechanism. Follow-up posted on <https://github.com/goldjg/WhereMyMVPsAt/issues/2>.

- **API console `$filter` frontend bug.** Same request that works via `curl` with `%27`-encoded single quotes returns 0 rows through the console UI. Not blocking us (our code URL-encodes correctly via `httpx.params`), but flagged in the same issue comment so other MVPs don't get stuck.

**When both are fixed:** flip `wheremymvpsat.enabled: true`, set `user_id: royklo`, add `WHEREMYMVPSAT_PAT` secret with `speakers:read` scope, and the workflow picks up conferences automatically on the next run.

## Other

_(none right now - add here as things come up)_
