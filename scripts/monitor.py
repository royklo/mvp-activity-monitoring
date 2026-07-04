"""Nightly MVP activity monitor. See README.md."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yml"
STATE_PATH = ROOT / ".state" / "seen.json"
ACTIVITIES = ROOT / "activities"
TEMPLATE_PATH = ROOT / "templates" / "activity_template.md"

MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"

# Branch-name suffix per Activity Type.
ACTIVITY_TYPE_SLUGS = {
    "Blog": "blog",
    "Podcast": "podcast",
    "Webinar/Online Training/Video/Livestream": "webinar",
    "Content Feedback and Editing": "feedback",
    "Online Support": "support",
    "Open Source/Project/Sample code/Tools": "opensource",
    "Product Feedback": "product-feedback",
    "Mentorship/Coaching": "mentorship",
    "Speaker/Presenter at Microsoft Event": "event",
    "Speaker/Presenter at Third-party Event": "event",
    "User Group Owner": "usergroup",
}


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text()) or {}


def load_state() -> set[str]:
    if STATE_PATH.exists():
        return set(json.loads(STATE_PATH.read_text()))
    return set()


def save_state(seen: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(sorted(seen), indent=2) + "\n")


def gather_items(sources: list[str]):
    for source in sources:
        parsed = feedparser.parse(source)
        if parsed.entries:
            for entry in parsed.entries:
                yield {
                    "url": entry.get("link", source),
                    "title": (entry.get("title") or "").strip(),
                    "summary": _strip_html(entry.get("summary", "")),
                    "published": entry.get("published", ""),
                    "published_parsed": entry.get("published_parsed"),
                }
            continue
        page = _fetch_page(source)
        if page is None:
            continue
        yield {
            "url": source,
            "title": _extract_title(page),
            "summary": _extract_meta_description(page),
            "published": "",
        }


def _fetch_page(url: str) -> str | None:
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except httpx.HTTPError as exc:
        print(f"! failed to fetch {url}: {exc}", file=sys.stderr)
        return None


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return _strip_html(m.group(1)).strip() if m else ""


def _extract_meta_description(html: str) -> str:
    for pattern in (
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
    ):
        m = re.search(pattern, html, re.I)
        if m:
            return m.group(1).strip()
    return ""


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def parse_start_date(value) -> "date | None":
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        print(f"! invalid start_date '{value}' - expected YYYY-MM-DD; ignoring", file=sys.stderr)
        return None


def is_after_start_date(item: dict, start_date: "date | None") -> bool:
    # No cutoff or no parseable date -> pass through.
    if start_date is None:
        return True
    st = item.get("published_parsed")
    if st is None:
        return True
    return date(st.tm_year, st.tm_mon, st.tm_mday) >= start_date


def matches_keywords(item: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    hay = f"{item['title']} {item['summary']} {item['url']}".lower()
    return any(k.lower() in hay for k in keywords)


def matches_exclude(item: dict, exclude_keywords: list[str]) -> bool:
    if not exclude_keywords:
        return False
    hay = f"{item['title']} {item['summary']} {item['url']}".lower()
    return any(k.lower() in hay for k in exclude_keywords)


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/") or parsed.netloc
    slug = re.sub(r"[^a-z0-9-]+", "-", path.lower()).strip("-")
    return slug[:80] or "activity"


def call_github_models(prompt: str, token: str, model: str) -> str:
    r = httpx.post(
        MODELS_ENDPOINT,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


TECH_AREAS_PATH = ROOT / "references" / "technology-areas.md"
ACTIVITY_TYPES_PATH = ROOT / "references" / "activity-types.md"


def build_prompt(item: dict, template: str) -> str:
    tech_areas = TECH_AREAS_PATH.read_text() if TECH_AREAS_PATH.exists() else ""
    activity_types = ACTIVITY_TYPES_PATH.read_text() if ACTIVITY_TYPES_PATH.exists() else ""
    return f"""You are drafting a Microsoft MVP activity tracking entry from a piece of online content.

Source item:
- URL: {item['url']}
- Title: {item['title']}
- Summary / excerpt: {item['summary']}
- Published (raw): {item['published']}

Return ONLY the filled-in markdown from the template below. Preserve the exact structure and headings.

Rules:
- Activity Type: default "Blog". Only choose another value if the source clearly matches it (e.g. a podcast RSS -> "Podcast"; a YouTube/Vimeo feed -> "Webinar/Online Training/Video/Livestream"; an event or session page -> "Speaker/Presenter at Microsoft Event" or "Speaker/Presenter at Third-party Event"; an open-source repo -> "Open Source/Project/Sample code/Tools"). Pick verbatim from the Activity Types reference below.
- Primary / Additional Technology Area: pick ONE value verbatim from the Technology Areas reference below, chosen from what the content is actually about. Never fall back to a hard-coded default. If the content genuinely does not map to any listed area, write "(uncertain - please review)" for that field instead of guessing.
- Title: max 100 characters.
- Description: 2 short paragraphs, max 1000 characters total. Paragraph 1 = what the content covers; paragraph 2 = impact. Program-reviewer voice, not peer-to-peer.
- Private Description: MVP-only context, max 1000 characters. One honest sentence is fine if nothing extra to add.
- Target Audience: infer from the content. Choose "Developer" for code/API-heavy content, "Technical Decision Maker" for governance or architecture, "Business Decision Maker" for strategy/ROI content, "IT Pro" for hands-on ops/admin content, "Student" for beginner tutorials. Never fall back to a hard-coded default; pick what actually fits.
- Role: default "Author" (use "Contributor" only if the MVP was not the primary creator). Special enums per type: Mentorship/Coaching = Organizer | Mentor | Other; User Group Owner = Organizer | Other.
- Quantity: always 1.
- Activity URL: use the Source URL verbatim.
- Type-specific fields section: emit ONLY the sub-fields that match the chosen Activity Type. Omit the whole section if the type has no extras (see the template).
- For any numeric field you cannot derive from the source (views, sessions, attendees), leave the literal placeholder "(fill from analytics before submitting)".
- Use regular hyphens, never em-dashes.
- Do not fabricate metrics, dates, or facts not present in the source item.

===== Activity Types reference =====
{activity_types}

===== Technology Areas reference =====
{tech_areas}

===== Template to fill =====
{template}
"""


def main() -> int:
    config = load_config()
    sources = config.get("sources") or []
    keywords = config.get("keywords") or []
    exclude_keywords = config.get("exclude_keywords") or []
    start_date = parse_start_date(config.get("start_date"))
    model = config.get("model") or "openai/gpt-4o"

    if not sources:
        print("config.yml has no sources - nothing to do")
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("! GITHUB_TOKEN not set", file=sys.stderr)
        return 1

    template = TEMPLATE_PATH.read_text()
    seen = load_state()

    new_items = []
    # start_date and exclude misses don't get marked seen, so loosening
    # either config value later resurfaces the items on the next run.
    for item in gather_items(sources):
        if not item["url"] or item["url"] in seen:
            continue
        if not is_after_start_date(item, start_date):
            continue
        if matches_exclude(item, exclude_keywords):
            continue
        if not matches_keywords(item, keywords):
            seen.add(item["url"])
            continue
        new_items.append(item)

    if not new_items:
        print("no new items")
        save_state(seen)
        return 0

    ACTIVITIES.mkdir(exist_ok=True)
    today = date.today().isoformat()
    types_found: set[str] = set()
    for item in new_items:
        try:
            md = call_github_models(build_prompt(item, template), token, model)
        except httpx.HTTPError as exc:
            print(f"! model call failed for {item['url']}: {exc}", file=sys.stderr)
            continue
        path = ACTIVITIES / f"{today}-{slug_from_url(item['url'])}.md"
        path.write_text(md.rstrip() + "\n")
        seen.add(item["url"])
        activity_type = _extract_activity_type(md)
        if activity_type:
            types_found.add(activity_type)
        print(f"wrote {path.relative_to(ROOT)}")

    save_state(seen)
    _emit_workflow_outputs(types_found)
    return 0


def _extract_activity_type(md: str) -> str | None:
    m = re.search(r"^##\s+Activity Type\s*\n+([^\n]+)", md, re.M)
    return m.group(1).strip() if m else None


def _emit_workflow_outputs(types_found: set[str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    slugs = sorted({ACTIVITY_TYPE_SLUGS.get(t, "other") for t in types_found}) or ["empty"]
    with open(output_path, "a") as f:
        f.write(f"has_new={'true' if types_found else 'false'}\n")
        f.write(f"types={'-'.join(slugs)}\n")


def _self_check() -> None:
    assert slug_from_url("https://rksolutions.nl/posts/macos-laps/") == "posts-macos-laps"
    assert slug_from_url("https://example.com/") == "example-com"
    assert matches_keywords({"title": "Intune tip", "summary": "", "url": ""}, ["intune"]) is True
    assert matches_keywords({"title": "Random", "summary": "", "url": ""}, ["intune"]) is False
    assert matches_keywords({"title": "x", "summary": "", "url": ""}, []) is True
    assert _extract_title("<title>Hello  World</title>") == "Hello  World"
    assert _extract_meta_description(
        '<meta name="description" content="A summary here">'
    ) == "A summary here"
    assert _extract_activity_type("## Activity Type\nBlog\n") == "Blog"
    assert _extract_activity_type(
        "# MVP Activity: X\n\n## Activity Type\nPodcast\n\n## Title\nY"
    ) == "Podcast"
    assert _extract_activity_type("## Title\nNo activity type here") is None
    assert ACTIVITY_TYPE_SLUGS["Speaker/Presenter at Microsoft Event"] == "event"
    assert ACTIVITY_TYPE_SLUGS["Speaker/Presenter at Third-party Event"] == "event"
    assert parse_start_date(None) is None
    assert parse_start_date("") is None
    assert parse_start_date("not-a-date") is None
    assert parse_start_date("2026-07-04") == date(2026, 7, 4)
    import time as _time
    _st = _time.struct_time((2026, 7, 4, 12, 0, 0, 0, 0, 0))
    _st_old = _time.struct_time((2025, 1, 1, 12, 0, 0, 0, 0, 0))
    assert is_after_start_date({"published_parsed": _st}, date(2026, 1, 1)) is True
    assert is_after_start_date({"published_parsed": _st_old}, date(2026, 1, 1)) is False
    assert is_after_start_date({"published_parsed": None}, date(2026, 1, 1)) is True
    assert is_after_start_date({"published_parsed": _st_old}, None) is True
    assert matches_exclude({"title": "About Inforcer", "summary": "", "url": ""}, ["inforcer"]) is True
    assert matches_exclude({"title": "Something else", "summary": "", "url": ""}, ["inforcer"]) is False
    assert matches_exclude({"title": "x", "summary": "", "url": ""}, []) is False
    print("self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        sys.exit(main())
