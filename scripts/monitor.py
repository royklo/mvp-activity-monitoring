"""Nightly MVP activity monitor. See README.md."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date
from itertools import chain
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
TECH_AREAS_PATH = ROOT / "references" / "technology-areas.md"
ACTIVITY_TYPES_PATH = ROOT / "references" / "activity-types.md"
CUSTOM_INSTRUCTIONS_PATH = ROOT / "custom-instructions.md"

MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MAX_BODY_CHARS = 6000  # cap so a huge post doesn't blow the prompt

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


def load_custom_instructions() -> str:
    # Return the raw file only when it holds content outside HTML comments.
    if not CUSTOM_INSTRUCTIONS_PATH.exists():
        return ""
    raw = CUSTOM_INSTRUCTIONS_PATH.read_text()
    stripped = re.sub(r"<!--.*?-->", "", raw, flags=re.S).strip()
    return raw if stripped else ""


def _normalize_sources(sources):
    """Yield (url, per_source_config) tuples. Accepts either bare URL strings
    or dicts with a `url` key and optional `keywords` / `exclude_keywords`
    overrides."""
    for src in sources or []:
        if isinstance(src, str):
            yield src, {}
        elif isinstance(src, dict) and src.get("url"):
            yield src["url"], src


def gather_items(sources):
    for source, src_cfg in _normalize_sources(sources):
        parsed = feedparser.parse(source)
        if parsed.entries:
            for entry in parsed.entries:
                yield {
                    "url": entry.get("link", source),
                    "title": (entry.get("title") or "").strip(),
                    "summary": _pick_body(entry),
                    "tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
                    "published": entry.get("published", ""),
                    "published_parsed": entry.get("published_parsed"),
                    "_source_cfg": src_cfg,
                }
            continue
        page = _fetch_page(source)
        if page is None:
            continue
        yield {
            "url": source,
            "title": _extract_title(page),
            "summary": _extract_meta_description(page),
            "tags": [],
            "published": "",
            "_source_cfg": src_cfg,
        }


def gather_wheremymvpsat(config: dict):
    wmma = config.get("wheremymvpsat") or {}
    if not wmma.get("enabled"):
        return
    user_id = wmma.get("user_id")
    if not user_id:
        print("! wheremymvpsat.enabled=true but user_id is unset", file=sys.stderr)
        return
    pat = os.environ.get("WHEREMYMVPSAT_PAT")
    if not pat:
        print("! wheremymvpsat.enabled=true but WHEREMYMVPSAT_PAT is unset", file=sys.stderr)
        return
    base = wmma.get("base_url", "https://wheremymvps.at/api/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/json"}

    try:
        r = httpx.get(f"{base}/speakers", params={"$filter": f"userId eq '{user_id}'"}, headers=headers, timeout=30)
        r.raise_for_status()
        rows = r.json().get("value", [])
    except httpx.HTTPError as exc:
        print(f"! wheremymvpsat /speakers failed: {exc}", file=sys.stderr)
        return
    if not rows:
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


def _pick_body(entry) -> str:
    # Prefer entry.content[0].value (full body) over entry.summary (excerpt).
    content = entry.get("content") or []
    if content and isinstance(content, list):
        raw = content[0].get("value") if isinstance(content[0], dict) else ""
    else:
        raw = entry.get("summary", "")
    return _strip_html(raw)[:MAX_BODY_CHARS]


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


def _parse_iso_struct(iso_date: str | None):
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date[:10])
    except ValueError:
        return None
    return time.struct_time((d.year, d.month, d.day, 0, 0, 0, 0, 0, 0))


def _struct_time_to_date(st) -> date | None:
    if st is None:
        return None
    return date(st.tm_year, st.tm_mon, st.tm_mday)


def parse_start_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        print(f"! invalid start_date '{value}' - expected YYYY-MM-DD; ignoring", file=sys.stderr)
        return None


def is_after_start_date(item: dict, start_date: date | None) -> bool:
    if start_date is None:
        return True
    d = _struct_time_to_date(item.get("published_parsed"))
    return True if d is None else d >= start_date


def build_filter_prompt(item: dict, keywords: list[str], exclude_keywords: list[str]) -> str:
    """Semantic pre-filter: ask the model whether the content is on-topic.

    Substring matching drops posts that MENTION a term but aren't about it
    ("my name is Roy, I work for Inforcer, and this post is on Intune...")
    and misses posts that ARE about a topic but never say the exact string
    in the title. Passing the keywords/exclude_keywords as topic hints and
    letting the model read the actual content gives accurate filtering.
    """
    inc = "\n".join(f"- {k}" for k in keywords) if keywords else "(no include filter - accept anything on-topic for an MVP)"
    exc = "\n".join(f"- {k}" for k in exclude_keywords) if exclude_keywords else "(nothing to exclude)"
    tags = ", ".join(item.get("tags") or []) or "(none)"
    return f"""Decide whether the content below should become a Microsoft MVP program activity entry.

Content:
- Title: {item['title']}
- Tags (author-provided): {tags}
- Body excerpt: {item['summary']}

Topics the MVP tracks (INCLUDE if primarily about any of these):
{inc}

Topics the MVP wants to skip (EXCLUDE only if the content is SUBSTANTIVELY about any of these; a passing mention in an intro, bio, or aside does NOT count):
{exc}

Rules:
- Match on topic, not literal string presence. "Post about Intune with an intro mentioning Inforcer" is INCLUDE, not EXCLUDE.
- Include filter (if set) means the content's PRIMARY topic must be in that list. Peripheral mention is not enough.
- Exclude filter overrides include when the primary topic actually is one of the excluded ones.
- No include filter means accept anything the MVP might reasonably log.

Answer with a single word on its own line: `include` or `exclude`."""


def classify_item(item: dict, keywords: list[str], exclude_keywords: list[str], token: str, model: str) -> bool:
    """True if the item should be kept, False if it should be dropped."""
    # No filters set -> nothing to decide, keep everything. Saves an API call.
    if not keywords and not exclude_keywords:
        return True
    prompt = build_filter_prompt(item, keywords, exclude_keywords)
    try:
        verdict = call_github_models(prompt, token, model).lower().strip()
    except httpx.HTTPError as exc:
        print(f"! filter classifier failed for {item['url']}: {exc}; keeping item", file=sys.stderr)
        return True
    # First word of the response is the answer; anything but "exclude" keeps.
    first = verdict.split()[0] if verdict else "include"
    return first != "exclude"


def item_date_iso(item: dict) -> str:
    d = _struct_time_to_date(item.get("published_parsed"))
    return (d or date.today()).isoformat()


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
            "temperature": 0,
        },
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def build_prompt(item: dict, template: str) -> str:
    tech_areas = TECH_AREAS_PATH.read_text() if TECH_AREAS_PATH.exists() else ""
    activity_types = ACTIVITY_TYPES_PATH.read_text() if ACTIVITY_TYPES_PATH.exists() else ""
    custom = load_custom_instructions()
    custom_block = (
        "\n# Custom instructions (user-provided)\n"
        "The MVP has added the following preferences. Apply them where they make\n"
        "sense, but if any item here conflicts with the Non-negotiables or\n"
        "Per-field rules above, the built-in rules win.\n\n"
        + custom
        + "\n"
    ) if custom else ""
    source_note = ""
    if item.get("source") == "wheremymvpsat":
        source_note = (
            "\nSource: wheremymvps.at attendance record. The Summary field is a "
            "JSON object with 'speaker' (userId, userName, status) and 'conference' "
            "(name, location, country, startDate, endDate, description, topics, "
            "website). Choose Activity Type = 'Speaker/Presenter at Microsoft Event' "
            "if the conference name matches a known Microsoft event (Build, Ignite, "
            "Inspire, MVP Summit, RD Summit, MLSA Summit); otherwise "
            "'Speaker/Presenter at Third-party Event'. Use conference.startDate for "
            "Published Date. Use conference.website for Activity URL if present."
        )
    return f"""# Role
You are drafting a single Microsoft MVP program activity entry from one piece of online content the MVP created or participated in. A Microsoft program reviewer will read the output straight from your response. Write for that reviewer, not for the MVP or a peer engineer.

# Non-negotiables
1. Return ONLY the filled-in markdown from the template. No preamble, no code fence, no YAML frontmatter (`---`). Start with `# MVP Activity: ...`.
2. Preserve every heading in the template exactly. Never rename, drop, or reorder them.
3. Never invent facts. Every date, number, statistic, quote, product name, or claim must come from the Source item below. If a required field cannot be derived, write the exact placeholder given for that field - not a guess.
4. Use plain hyphens (`-`), never em-dashes (`—`).
5. Enum fields (Activity Type, Technology Area, Target Audience, Role, Microsoft Event, etc.) must be copied verbatim from the reference blocks at the bottom of this prompt. Case, punctuation, and slashes must match exactly.

# How to work through this
Follow these steps in order. Do not skip.

Step 1. Read Title, Tags, Body, and Published from the Source item.
Step 2. Decide Activity Type (see rules below). Note the type-specific fields it requires.
Step 3. Anchor on the Tags line - it is the AUTHOR'S OWN CLASSIFICATION of the content. Use it as the primary signal for Technology Area choices. The body is context; the tags are ground truth for what the content is about.
Step 4. Pick Primary Technology Area, then decide whether an Additional Technology Area is warranted (see the strict rule below).
Report each Technology Area verbatim from the Technology Areas reference. The reference is grouped for browsing; only the leaf values are legal outputs.
Step 5. Fill in the descriptive fields (Title, Description, Private Description) using only material from the Source item.
Step 6. List every Target Audience the content serves.
Step 7. Fill Published Date, Role, Quantity, Activity URL, and the Type-specific fields block for the chosen Activity Type.

# Per-field rules

## Activity Type
Default `Blog`. Choose a different value ONLY when the source clearly matches one:
- Podcast RSS or audio feed -> `Podcast`
- YouTube/Vimeo/livestream feed -> `Webinar/Online Training/Video/Livestream`
- Conference session page, event listing, meetup -> `Speaker/Presenter at Microsoft Event` if the conference is a known Microsoft event (Build, Ignite, Inspire, MVP Summit, RD Summit, MLSA Summit); otherwise `Speaker/Presenter at Third-party Event`
- Public repo or code sample project -> `Open Source/Project/Sample code/Tools`
- Community forum post, StackOverflow answer, Discord/Slack support thread -> `Online Support`
- 1-on-1 or small-group teaching/coaching -> `Mentorship/Coaching`
- Running or leading a user group -> `User Group Owner`
- Editing/reviewing content -> `Content Feedback and Editing`
- Product feedback to Microsoft -> `Product Feedback`

## Primary Technology Area
Pick exactly one value verbatim from the Technology Areas reference. Choose the SINGLE product the content is most centrally about. If nothing in the reference plausibly fits, write literally `(uncertain - please review)` - do not force a value.

## Additional Technology Areas
Only fill this when the content SUBSTANTIVELY covers a second Microsoft product. Substantive means multiple paragraphs, code samples, or configuration examples explicitly about that product. All three of the following DO NOT COUNT:
- A single passing mention in an intro or scenario ("A user opens Teams and...", "you might also use SharePoint...").
- A product name in an analogy or comparison ("similar to Outlook rules").
- A product name that only appears in a stack trace, screenshot title, or file path.

If the Tags line does not include the product AND the body does not substantively cover it, write literally `(no second area detected - please review)`. Do not force a value. The reviewer will decide whether to add one manually.

## Title
Max 100 characters. Prefer the source's own title; shorten only if it exceeds the limit.

## Description
Two short paragraphs, 1000 characters combined maximum, in program-reviewer voice (third person, no "you"). Paragraph 1: what the content covers - the concrete subject, key steps, tools, commands, or conclusions. Paragraph 2: impact - who it helps and what problem it saves them. No filler adjectives ("comprehensive", "in-depth", "cutting-edge"). No promotional language.

## Private Description
Max 1000 characters, MVP-only context: the trigger for creating the content, the documentation gap it fills, a customer/community pattern it addresses. Never include confidential customer names. If nothing meaningful to add beyond the public description, write one honest sentence to that effect.

## Target Audience
List EVERY audience the content genuinely serves, one per line as `- <value>`. Do not stop at one. Selection rules:
- `IT Pro`: hands-on ops/admin walkthrough, troubleshooting, configuration
- `Developer`: contains code, API/SDK usage, scripting, automation targeted at builders
- `Technical Decision Maker`: covers governance, compliance, architecture patterns, security posture, policy trade-offs
- `Business Decision Maker`: covers strategy, ROI, licensing, org-level decisions
- `Student`: beginner tutorial or foundational explainer
- `Other`: none of the above fit
Most technical MVP-blog posts serve at least two of these. A post that walks an admin through fixing a compliance issue and explains the underlying policy design serves `IT Pro` AND `Technical Decision Maker`.

## Published Date
Copy the source's published date verbatim. If the source has no parseable date, write `(unknown)`.

## Role
Default `Author`. Use `Contributor` only if the MVP was not the primary creator. For Mentorship/Coaching pick from `Organizer | Mentor | Other`. For User Group Owner pick from `Organizer | Other`.

## Quantity
Always `1`.

## Activity URL
Use the URL from the Source item verbatim.

## Type-specific fields
Emit ONLY the sub-fields for the Activity Type you picked. Omit the entire section if the type has no extras. Numeric fields you cannot derive from the source get the literal placeholder `(fill from analytics before submitting)`.
{custom_block}
# Source item
{source_note}
- URL: {item['url']}
- Title: {item['title']}
- Tags (from the feed, AUTHORITATIVE for topic classification): {', '.join(item.get('tags') or []) or '(none)'}
- Body: {item['summary']}
- Published (raw): {item['published']}

===== Activity Types reference =====
{activity_types}

===== Technology Areas reference =====
{tech_areas}

===== Template to fill =====
{template}
"""


def _extract_activity_type(md: str) -> str | None:
    m = re.search(r"^##\s+Activity Type\s*\n+([^\n]+)", md, re.M)
    return m.group(1).strip() if m else None


def _emit_workflow_outputs(types_found: set[str], auto_merge: bool) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    slugs = sorted({ACTIVITY_TYPE_SLUGS.get(t, "other") for t in types_found}) or ["empty"]
    with open(output_path, "a") as f:
        f.write(f"has_new={'true' if types_found else 'false'}\n")
        f.write(f"types={'-'.join(slugs)}\n")
        f.write(f"auto_merge={'true' if auto_merge else 'false'}\n")


def main() -> int:
    config = load_config()
    sources = config.get("sources") or []
    keywords = config.get("keywords") or []
    exclude_keywords = config.get("exclude_keywords") or []
    start_date = parse_start_date(config.get("start_date"))
    model = config.get("model") or "openai/gpt-4.1"
    auto_merge = bool(config.get("auto_merge"))

    wmma_enabled = bool((config.get("wheremymvpsat") or {}).get("enabled"))
    if not sources and not wmma_enabled:
        print("config.yml has no sources and wheremymvpsat is disabled - nothing to do")
        _emit_workflow_outputs(set(), auto_merge)
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("! GITHUB_TOKEN not set", file=sys.stderr)
        return 1

    template = TEMPLATE_PATH.read_text()
    seen = load_state()

    new_items = []
    classifier_rejects = 0
    total_rss_items = 0
    # start_date misses don't get marked seen, so moving start_date earlier
    # later resurfaces those items on the next run.
    for item in chain(gather_items(sources), gather_wheremymvpsat(config)):
        if item.get("source") != "wheremymvpsat":
            total_rss_items += 1
        if not item["url"] or item["url"] in seen:
            continue
        if not is_after_start_date(item, start_date):
            continue
        # Per-source overrides fall back to global when the key is missing
        # OR present-but-null (commented-only YAML). Explicit [] overrides.
        src_cfg = item.get("_source_cfg") or {}
        _src_ex = src_cfg.get("exclude_keywords")
        _src_kw = src_cfg.get("keywords")
        effective_exclude = _src_ex if _src_ex is not None else exclude_keywords
        effective_keywords = _src_kw if _src_kw is not None else keywords
        # wheremymvps.at rows already scope to this MVP via PAT+userId -
        # skip semantic filtering entirely for those.
        if item.get("source") != "wheremymvpsat" and (effective_keywords or effective_exclude):
            if not classify_item(item, effective_keywords or [], effective_exclude or [], token, model):
                classifier_rejects += 1
                seen.add(item["url"])
                print(f"filter dropped: {item['url']}", file=sys.stderr)
                continue
        new_items.append(item)

    if total_rss_items and classifier_rejects == total_rss_items:
        print(
            f"! the semantic filter dropped every one of the {total_rss_items} "
            "RSS items. Double-check `keywords` / `exclude_keywords` in "
            "config.yml - the topic hints may be too narrow.",
            file=sys.stderr,
        )

    if not new_items:
        print("no new items")
        save_state(seen)
        _emit_workflow_outputs(set(), auto_merge)
        return 0

    ACTIVITIES.mkdir(exist_ok=True)
    types_found: set[str] = set()
    for item in new_items:
        try:
            md = call_github_models(build_prompt(item, template), token, model)
        except httpx.HTTPError as exc:
            print(f"! model call failed for {item['url']}: {exc}", file=sys.stderr)
            continue
        path = ACTIVITIES / f"{item_date_iso(item)}-{slug_from_url(item['url'])}.md"
        path.write_text(md.rstrip() + "\n")
        seen.add(item["url"])
        activity_type = _extract_activity_type(md)
        if activity_type:
            types_found.add(activity_type)
        print(f"wrote {path.relative_to(ROOT)}")

    save_state(seen)
    _emit_workflow_outputs(types_found, auto_merge)
    return 0


def _self_check() -> None:
    assert slug_from_url("https://rksolutions.nl/posts/macos-laps/") == "posts-macos-laps"
    assert slug_from_url("https://example.com/") == "example-com"
    assert slug_from_url("https://example.com") == "example-com"  # no trailing slash
    assert slug_from_url("https://example.com/héllo-wörld/") == "h-llo-w-rld"
    assert slug_from_url("") == "activity"  # nothing usable -> fallback
    # _strip_html edge cases: nested, empty, malformed.
    assert _strip_html("<p><b>hi</b></p>") == "hi"
    assert _strip_html("") == ""
    assert _strip_html(None) == ""
    assert _strip_html("<p") == "<p"  # no closing '>' -> passthrough
    assert _strip_html("  <p>x</p>  ") == "x"
    # build_prompt shape check: drafter prompt exposes source metadata + template heading.
    _stub_tpl = "## Activity Type\n<value>\n\n## Title\n<value>\n"
    _bp = build_prompt(
        {"url": "https://ex.com/post", "title": "Sample title",
         "tags": ["Intune", "Entra"], "summary": "body", "published": "2026-07-01"},
        _stub_tpl,
    )
    assert "https://ex.com/post" in _bp
    assert "Sample title" in _bp
    assert "Intune, Entra" in _bp
    assert "## Activity Type" in _bp
    # build_filter_prompt shape: keywords, exclude, title all present in the output.
    _p = build_filter_prompt(
        {"title": "Intune tip", "tags": ["Intune"], "summary": "body"},
        ["Intune"], ["sponsored"],
    )
    assert "Intune tip" in _p and "Intune" in _p and "sponsored" in _p
    _p_none = build_filter_prompt({"title": "x", "tags": [], "summary": ""}, [], [])
    assert "no include filter" in _p_none and "nothing to exclude" in _p_none
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
    _st = time.struct_time((2026, 7, 4, 12, 0, 0, 0, 0, 0))
    _st_old = time.struct_time((2025, 1, 1, 12, 0, 0, 0, 0, 0))
    assert is_after_start_date({"published_parsed": _st}, date(2026, 1, 1)) is True
    assert is_after_start_date({"published_parsed": _st_old}, date(2026, 1, 1)) is False
    assert is_after_start_date({"published_parsed": None}, date(2026, 1, 1)) is True
    assert is_after_start_date({"published_parsed": _st_old}, None) is True
    # classify_item short-circuits when both filter lists are empty (no API call).
    assert classify_item({"title": "x", "summary": "", "tags": []}, [], [], "no-token", "no-model") is True
    # classify_item verdict parsing: swap the LLM call so we exercise pure logic.
    _real_call = globals()["call_github_models"]
    try:
        _item = {"title": "x", "summary": "y", "tags": [], "url": "u"}
        for verdict, expected in (
            ("include", True),
            ("exclude", False),
            ("exclude - off-topic bio mention", False),
            ("INCLUDE\n", True),
            ("", True),  # empty response defaults to include
        ):
            globals()["call_github_models"] = lambda p, t, m, _v=verdict: _v
            assert classify_item(_item, ["Intune"], [], "t", "m") is expected, verdict
    finally:
        globals()["call_github_models"] = _real_call
    assert item_date_iso({"published_parsed": _st}) == "2026-07-04"
    assert item_date_iso({"published_parsed": None}) == date.today().isoformat()
    assert _pick_body({"content": [{"value": "<p>hi</p>"}]}) == "hi"
    assert _pick_body({"summary": "<b>fallback</b>"}) == "fallback"
    assert _pick_body({"content": [{"value": "x" * 10000}]}) == "x" * MAX_BODY_CHARS
    assert _parse_iso_struct(None) is None
    assert _parse_iso_struct("") is None
    assert _parse_iso_struct("not-a-date") is None
    _pi = _parse_iso_struct("2026-07-04")
    assert _pi is not None and _pi.tm_year == 2026 and _pi.tm_mon == 7 and _pi.tm_mday == 4
    _norm = list(_normalize_sources(["https://a.example/feed"]))
    assert _norm == [("https://a.example/feed", {})]
    _norm = list(_normalize_sources([
        "https://a.example/feed",
        {"url": "https://b.example/feed", "keywords": ["Foo"]},
        {"no_url": True},
    ]))
    assert _norm[0] == ("https://a.example/feed", {})
    assert _norm[1][0] == "https://b.example/feed" and _norm[1][1]["keywords"] == ["Foo"]
    assert len(_norm) == 2  # entry without url is dropped
    assert list(_normalize_sources(None)) == []
    # Per-source vs global precedence is now enforced in main() around the
    # classifier call. Semantic classification itself is exercised via
    # build_filter_prompt (shape) and classify_item (short-circuit) above.
    # Shipped config must be valid YAML - guards against the "keywords: []
    # followed by commented example items" pattern that breaks the moment
    # a user un-comments a real item.
    parsed = load_config()
    assert isinstance(parsed, dict)
    assert isinstance(parsed.get("sources") or [], list)
    assert isinstance(parsed.get("keywords") or [], list)
    assert isinstance(parsed.get("exclude_keywords") or [], list)
    _real = CUSTOM_INSTRUCTIONS_PATH.read_text() if CUSTOM_INSTRUCTIONS_PATH.exists() else ""
    try:
        CUSTOM_INSTRUCTIONS_PATH.write_text("<!-- only a comment -->\n\n")
        assert load_custom_instructions() == ""
        CUSTOM_INSTRUCTIONS_PATH.write_text("<!-- comment -->\nreal note here\n")
        assert "real note here" in load_custom_instructions()
    finally:
        CUSTOM_INSTRUCTIONS_PATH.write_text(_real)
    import tempfile
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        tmp = f.name
    try:
        os.environ["GITHUB_OUTPUT"] = tmp
        _emit_workflow_outputs(set(), False)
        assert "has_new=false" in Path(tmp).read_text()
        assert "auto_merge=false" in Path(tmp).read_text()
        Path(tmp).write_text("")
        _emit_workflow_outputs({"Blog", "Podcast"}, True)
        out = Path(tmp).read_text()
        assert "has_new=true" in out
        assert "types=blog-podcast" in out
        assert "auto_merge=true" in out
    finally:
        os.environ.pop("GITHUB_OUTPUT", None)
        os.unlink(tmp)
    print("self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        sys.exit(main())
