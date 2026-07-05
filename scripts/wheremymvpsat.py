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


def gather_wheremymvpsat(config: dict):
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

    try:
        r = httpx.get(f"{base}/speakers", params={"$filter": f"userId eq '{user_id}'"}, headers=headers, timeout=30)
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
    if conf_ids:
        try:
            or_clause = " or ".join(f"id eq '{cid}'" for cid in conf_ids)
            r = httpx.get(f"{base}/conferences", params={"$filter": or_clause}, headers=headers, timeout=30)
            r.raise_for_status()
            for c in r.json().get("value", []):
                if isinstance(c, dict) and c.get("id"):
                    conferences[c["id"]] = c
            print(f"wheremymvpsat: /conferences enriched {len(conferences)}/{len(conf_ids)} records")
        except httpx.HTTPError as exc:
            print(f"! wheremymvpsat /conferences failed: {exc}", file=sys.stderr)

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
