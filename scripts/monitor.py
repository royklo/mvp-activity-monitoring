"""Nightly MVP activity monitor. See README.md."""
from __future__ import annotations

import json
import os
import re
import string
import sys
import time
from datetime import date
from functools import lru_cache
from itertools import chain
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import httpx
import yaml

from wheremymvpsat import gather_wheremymvpsat

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yml"
STATE_PATH = ROOT / ".state" / "seen.json"
ACTIVITIES = ROOT / "activities"
TEMPLATE_PATH = ROOT / "templates" / "activity_template.md"
TECH_AREAS_PATH = ROOT / "references" / "technology-areas.md"
ACTIVITY_TYPES_PATH = ROOT / "references" / "activity-types.md"
CUSTOM_INSTRUCTIONS_PATH = ROOT / "custom-instructions.md"
PROMPTS_DIR = ROOT / "prompts"
DRAFTER_DIR = PROMPTS_DIR / "drafter"

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
        else:
            print(f"! ignoring malformed source entry (needs a `url:` key): {src!r}", file=sys.stderr)


_HTTP_CLIENT: httpx.Client | None = None


def _http() -> httpx.Client:
    """Shared httpx client for LLM + fallback page fetches. Connection-level
    retries (DNS, connect timeouts) handled by the transport; 5xx retries are
    handled in call_github_models."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.Client(
            transport=httpx.HTTPTransport(retries=3),
            follow_redirects=True,
        )
    return _HTTP_CLIENT


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
        r = _http().get(url, timeout=20)
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
    return _filter_template().safe_substitute(
        title=item["title"],
        tags=tags,
        body=item["summary"],
        include_topics=inc,
        exclude_topics=exc,
    )


@lru_cache(maxsize=1)
def _filter_template() -> string.Template:
    return string.Template((PROMPTS_DIR / "filter.md").read_text())


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
    """Call GitHub Models with exponential-backoff retry on 5xx and network errors.
    4xx errors bubble immediately - client-side bugs don't self-heal."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    delays = [1, 3, 9]  # ~13s across 3 retries; final attempt has no sleep after it
    for attempt in range(len(delays) + 1):
        try:
            r = _http().post(MODELS_ENDPOINT, headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500 or attempt == len(delays):
                raise
            print(f"! LLM {exc.response.status_code} on attempt {attempt + 1}, retrying in {delays[attempt]}s", file=sys.stderr)
        except httpx.HTTPError as exc:
            if attempt == len(delays):
                raise
            print(f"! LLM network error on attempt {attempt + 1} ({exc}), retrying in {delays[attempt]}s", file=sys.stderr)
        time.sleep(delays[attempt])
    raise RuntimeError("unreachable")  # loop always returns or raises


# Prompt files are static across a run - cache them so a 20-item run doesn't
# do 20x the same disk reads. custom-instructions.md is deliberately NOT
# cached because test_monitor.py mutates it in-place.
@lru_cache(maxsize=1)
def _drafter_template() -> string.Template:
    parts = [p.read_text() for p in sorted(DRAFTER_DIR.glob("[0-9]*.md"))]
    return string.Template("".join(parts))


@lru_cache(maxsize=1)
def _tech_areas() -> str:
    return TECH_AREAS_PATH.read_text() if TECH_AREAS_PATH.exists() else ""


@lru_cache(maxsize=1)
def _activity_types() -> str:
    return ACTIVITY_TYPES_PATH.read_text() if ACTIVITY_TYPES_PATH.exists() else ""


@lru_cache(maxsize=1)
def _custom_wrapper() -> string.Template:
    return string.Template((PROMPTS_DIR / "custom_instructions_wrapper.md").read_text())


@lru_cache(maxsize=1)
def _wmma_source_note() -> str:
    return (PROMPTS_DIR / "wmma_source_note.md").read_text()


def build_prompt(item: dict, template: str) -> str:
    custom = load_custom_instructions()
    custom_block = _custom_wrapper().safe_substitute(custom_instructions=custom) if custom else ""
    source_note = _wmma_source_note() if item.get("source") == "wheremymvpsat" else ""
    return _drafter_template().safe_substitute(
        custom_block=custom_block,
        source_note=source_note,
        url=item["url"],
        title=item["title"],
        tags=", ".join(item.get("tags") or []) or "(none)",
        body=item["summary"],
        published=item["published"],
        activity_types=_activity_types(),
        tech_areas=_tech_areas(),
        template=template,
    )


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

    print(f"config: {len(sources)} sources, model={model}, start_date={start_date or 'none'}")
    print(f"        global keywords={keywords or '(none)'}, exclude={exclude_keywords or '(none)'}")

    template = TEMPLATE_PATH.read_text()
    seen = load_state()

    new_items = []
    stats = {"seen": 0, "pre_start": 0, "included": 0, "excluded": 0, "rss_total": 0, "wmma_total": 0}
    # start_date misses don't get marked seen, so moving start_date earlier
    # later resurfaces those items on the next run.
    for item in chain(gather_items(sources), gather_wheremymvpsat(config, _http())):
        is_wmma = item.get("source") == "wheremymvpsat"
        stats["wmma_total" if is_wmma else "rss_total"] += 1
        url = item["url"]
        if not url or url in seen:
            stats["seen"] += 1
            print(f"  seen  {url}")
            continue
        if not is_after_start_date(item, start_date):
            stats["pre_start"] += 1
            print(f"  old   {url}  (before start_date)")
            continue
        src_cfg = item.get("_source_cfg") or {}
        _src_ex = src_cfg.get("exclude_keywords")
        _src_kw = src_cfg.get("keywords")
        effective_exclude = _src_ex if _src_ex is not None else exclude_keywords
        effective_keywords = _src_kw if _src_kw is not None else keywords
        if not is_wmma and (effective_keywords or effective_exclude):
            if not classify_item(item, effective_keywords or [], effective_exclude or [], token, model):
                stats["excluded"] += 1
                seen.add(url)
                print(f"  exc   {url}  (classifier: exclude)")
                continue
        stats["included"] += 1
        print(f"  inc   {url}")
        new_items.append(item)

    print(
        f"filter summary: seen={stats['seen']} "
        f"pre_start_date={stats['pre_start']} "
        f"included={stats['included']} excluded={stats['excluded']} "
        f"(from {stats['rss_total']} RSS + {stats['wmma_total']} wheremymvpsat)"
    )
    if stats["rss_total"] and stats["excluded"] == stats["rss_total"] - stats["seen"] - stats["pre_start"]:
        if stats["excluded"] > 0:
            print(
                "! the semantic filter dropped every RSS item that made it through the pre-checks. "
                "Double-check `keywords` / `exclude_keywords` - the topic hints may be too narrow.",
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


if __name__ == "__main__":
    sys.exit(main())
