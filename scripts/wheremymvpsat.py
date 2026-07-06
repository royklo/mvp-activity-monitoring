"""wheremymvps.at conference-attendance integration for monitor.py.

See README/SETUP for enable + PAT setup. The API returns records for the
`userId` you filter on, case-sensitive, no leading '@'. A verified MVP's
PAT can read other MVPs' records; the scope isn't self-only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date

import httpx


CONF_CHUNK = 20  # OData $filter OR-clause size; enough per hop, small enough to fit URL limits


def gather_wheremymvpsat(config: dict, client: httpx.Client | None = None):
    wmma = config.get("wheremymvpsat") or {}
    if not wmma.get("enabled"):
        print("wheremymvpsat: disabled (config: enabled=false)")
        return
    user_id = wmma.get("user_id")
    if not user_id:
        print("! wheremymvpsat.enabled=true but user_id is unset - skipping", file=sys.stderr)
        return
    pat = os.environ.get("WHEREMYMVPSAT_PAT")
    if not pat:
        print("! wheremymvpsat.enabled=true but WHEREMYMVPSAT_PAT secret is missing - skipping", file=sys.stderr)
        return
    base = wmma.get("base_url", "https://wheremymvps.at/api/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
    print(f"wheremymvpsat: enabled, user_id={user_id}")
    # Callers can inject a shared client; fall back to a one-shot Client so the
    # module stays usable standalone (tests, one-off scripts).
    owned = client is None
    http = client if client is not None else httpx.Client()
    try:
        try:
            r = http.get(f"{base}/speakers", params={"$filter": f"userId eq '{user_id}'"}, headers=headers, timeout=30)
            r.raise_for_status()
            rows = r.json().get("value", [])
        except httpx.HTTPError as exc:
            print(f"! wheremymvpsat /speakers failed: {exc}", file=sys.stderr)
            return
        print(f"wheremymvpsat: /speakers filter=userId eq '{user_id}' -> {len(rows)} records")
        if not rows:
            print(
                f"wheremymvpsat: 0 records for userId '{user_id}'. Note the value is "
                "case-sensitive and must NOT include the leading '@' (profile shown as "
                "'@Jane-Doe' is stored as 'Jane-Doe'). If the id is already correct, "
                "add events on your wheremymvps.at profile first."
            )
            return

        conf_ids = sorted({row["conferenceId"] for row in rows if row.get("conferenceId")})
        conferences: dict[str, dict] = {}
        # Chunk the OR-clause so a large attendance history doesn't blow the URL length.
        for i in range(0, len(conf_ids), CONF_CHUNK):
            chunk = conf_ids[i:i + CONF_CHUNK]
            try:
                or_clause = " or ".join(f"id eq '{cid}'" for cid in chunk)
                r = http.get(f"{base}/conferences", params={"$filter": or_clause}, headers=headers, timeout=30)
                r.raise_for_status()
                for c in r.json().get("value", []):
                    if isinstance(c, dict) and c.get("id"):
                        conferences[c["id"]] = c
            except httpx.HTTPError as exc:
                print(f"! wheremymvpsat /conferences chunk {i}-{i+len(chunk)} failed: {exc}", file=sys.stderr)
        print(f"wheremymvpsat: /conferences enriched {len(conferences)}/{len(conf_ids)} records")
    finally:
        if owned:
            http.close()

    for row in rows:
        conf = conferences.get(row.get("conferenceId", ""), {})
        merged = {"speaker": row, "conference": conf}
        stable = conf.get("website") or f"wmma://conference/{row.get('conferenceId')}/user/{user_id}"
        yield {
            "url": stable,
            "title": conf.get("name") or f"Conference {row.get('conferenceId', '?')}",
            "summary": json.dumps(merged, default=str, ensure_ascii=False)[:2000],
            "published": conf.get("startDate", ""),
            "published_parsed": _parse_iso_struct(conf.get("startDate")),
            "source": "wheremymvpsat",
        }


def _parse_iso_struct(iso_date: str | None):
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date[:10])
    except ValueError:
        return None
    return time.struct_time((d.year, d.month, d.day, 0, 0, 0, 0, 0, 0))
