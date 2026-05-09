"""Property-based tests for formatter module."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from keylol_mcp.formatter import to_markdown, to_json
from keylol_mcp.models import PostData, ThreadMeta, ThreadData


# --- Strategies ---

# Use alphanumeric text to avoid YAML quoting edge cases
safe_text = st.from_regex(r"[A-Za-z0-9 ]{1,30}", fullmatch=True)
# tid is numeric string
tid_strategy = st.from_regex(r"[0-9]{4,8}", fullmatch=True)
# date_text like "2026-4-9 12:30"
date_text_strategy = st.from_regex(r"20[0-9]{2}-[0-9]{1,2}-[0-9]{1,2} [0-9]{2}:[0-9]{2}", fullmatch=True)
# URL
url_strategy = tid_strategy.map(lambda tid: f"https://keylol.com/t{tid}-1-1")
# scraped_at timestamp
scraped_at_strategy = st.from_regex(r"20[0-9]{2}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", fullmatch=True)


@st.composite
def post_data_strategy(draw):
    """Generate a PostData instance."""
    return PostData(
        author=draw(safe_text),
        date_text=draw(date_text_strategy),
        content_html=draw(safe_text),
        content_md=draw(safe_text),
    )


@st.composite
def thread_meta_strategy(draw):
    """Generate a ThreadMeta instance."""
    tid = draw(tid_strategy)
    return ThreadMeta(
        tid=tid,
        title=draw(safe_text),
        url=f"https://keylol.com/t{tid}-1-1",
        author=draw(safe_text),
        date_text=draw(date_text_strategy),
    )


@st.composite
def thread_data_strategy(draw):
    """Generate a ThreadData instance with optional main_post and 0-5 comments."""
    meta = draw(thread_meta_strategy())
    main_post = draw(st.one_of(st.none(), post_data_strategy()))
    comments = draw(st.lists(post_data_strategy(), min_size=0, max_size=5))
    scraped_at = draw(scraped_at_strategy)
    return ThreadData(
        meta=meta,
        main_post=main_post,
        comments=comments,
        scraped_at=scraped_at,
    )


# --- Property Tests ---


@given(thread=thread_data_strategy())
@settings(max_examples=100)
def test_property_10_markdown_output_format(thread):
    """Feature: keylol-mcp-server, Property 10: Markdown 输出格式

    **Validates: Requirements 6.1**

    For any valid ThreadData, the Markdown formatter output should start with
    valid YAML front-matter delimited by `---` and contain all required metadata
    fields (title, author, date, url, tid, scraped_at).
    """
    result = to_markdown(thread)

    # Output starts with "---\n"
    assert result.startswith("---\n"), (
        f"Markdown output does not start with '---\\n'.\n"
        f"Output starts with: {result[:50]!r}"
    )

    # Contains a second "---" delimiter (closing front-matter)
    lines = result.split("\n")
    assert lines[0] == "---", "First line should be '---'"
    # Find the closing delimiter (should be after the first line)
    closing_idx = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            closing_idx = i
            break
    assert closing_idx is not None, (
        "No closing '---' delimiter found for YAML front-matter.\n"
        f"Output: {result[:200]!r}"
    )

    # Extract front-matter content
    front_matter = "\n".join(lines[1:closing_idx])

    # Verify all required fields are present in front-matter
    required_fields = ["title", "author", "date", "url", "tid", "scraped_at"]
    for field in required_fields:
        assert f"{field}:" in front_matter, (
            f"Required field '{field}' not found in YAML front-matter.\n"
            f"Front-matter: {front_matter!r}"
        )

    # Verify field values match input ThreadData
    assert thread.meta.title in front_matter, (
        f"Title value '{thread.meta.title}' not found in front-matter.\n"
        f"Front-matter: {front_matter!r}"
    )
    assert thread.meta.author in front_matter, (
        f"Author value '{thread.meta.author}' not found in front-matter.\n"
        f"Front-matter: {front_matter!r}"
    )
    assert thread.meta.date_text in front_matter, (
        f"Date value '{thread.meta.date_text}' not found in front-matter.\n"
        f"Front-matter: {front_matter!r}"
    )
    assert thread.meta.url in front_matter, (
        f"URL value '{thread.meta.url}' not found in front-matter.\n"
        f"Front-matter: {front_matter!r}"
    )
    assert thread.meta.tid in front_matter, (
        f"TID value '{thread.meta.tid}' not found in front-matter.\n"
        f"Front-matter: {front_matter!r}"
    )
    assert thread.scraped_at in front_matter, (
        f"scraped_at value '{thread.scraped_at}' not found in front-matter.\n"
        f"Front-matter: {front_matter!r}"
    )


@given(thread=thread_data_strategy())
@settings(max_examples=100)
def test_property_11_json_serialization_roundtrip(thread):
    """Feature: keylol-mcp-server, Property 11: JSON 序列化 round-trip

    **Validates: Requirements 6.2**

    For any valid ThreadData object, serializing to JSON then deserializing
    should produce an equivalent data structure with all fields preserved.
    """
    json_str = to_json(thread)

    # Should be valid JSON
    data = json.loads(json_str)

    # Verify meta fields are preserved
    assert data["meta"]["tid"] == thread.meta.tid
    assert data["meta"]["title"] == thread.meta.title
    assert data["meta"]["url"] == thread.meta.url
    assert data["meta"]["author"] == thread.meta.author
    assert data["meta"]["date_text"] == thread.meta.date_text
    assert data["meta"]["scraped_at"] == thread.scraped_at

    # Verify main_post
    if thread.main_post is None:
        assert data["main_post"] is None
    else:
        assert data["main_post"]["author"] == thread.main_post.author
        assert data["main_post"]["date_text"] == thread.main_post.date_text
        assert data["main_post"]["content_md"] == thread.main_post.content_md

    # Verify comments count and content
    assert len(data["comments"]) == len(thread.comments)
    for i, comment in enumerate(thread.comments):
        assert data["comments"][i]["author"] == comment.author
        assert data["comments"][i]["date_text"] == comment.date_text
        assert data["comments"][i]["content_md"] == comment.content_md
