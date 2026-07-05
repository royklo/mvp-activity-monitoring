"""Assert-based self-checks. Run: `python scripts/test_monitor.py`.

No frameworks, no fixtures. Exercises every pure helper in monitor.py and
wheremymvpsat.py. Network paths (`gather_items`, `gather_wheremymvpsat`,
`main`) are deliberately not covered - mocking them is more effort than
the harness weight is worth.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import monitor
from monitor import (
    ACTIVITY_TYPE_SLUGS,
    CUSTOM_INSTRUCTIONS_PATH,
    MAX_BODY_CHARS,
    _emit_workflow_outputs,
    _extract_activity_type,
    _extract_meta_description,
    _extract_title,
    _normalize_sources,
    _pick_body,
    _strip_html,
    build_filter_prompt,
    build_prompt,
    classify_item,
    is_after_start_date,
    item_date_iso,
    load_config,
    load_custom_instructions,
    parse_start_date,
    slug_from_url,
)
from wheremymvpsat import _parse_iso_struct


def main() -> None:
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
    _real_call = monitor.call_github_models
    try:
        _item = {"title": "x", "summary": "y", "tags": [], "url": "u"}
        for verdict, expected in (
            ("include", True),
            ("exclude", False),
            ("exclude - off-topic bio mention", False),
            ("INCLUDE\n", True),
            ("", True),  # empty response defaults to include
        ):
            monitor.call_github_models = lambda p, t, m, _v=verdict: _v
            assert classify_item(_item, ["Intune"], [], "t", "m") is expected, verdict
    finally:
        monitor.call_github_models = _real_call
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
    main()
