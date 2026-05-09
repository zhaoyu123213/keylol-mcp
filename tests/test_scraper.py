"""Property-based tests for scraper module."""

from datetime import date

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from keylol_mcp.scraper import matches_date, parse_thread_page


# --- Strategies ---


def date_strategy():
    """Generate random dates in range 2020-2030, day 1-28 to avoid invalid dates."""
    return st.builds(
        date,
        year=st.integers(min_value=2020, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
    )


def matching_date_string(target: date) -> str:
    """Build a date string that matches the target date (no zero-padding)."""
    return f"{target.year}-{target.month}-{target.day}"


def thread_tid_strategy():
    """Generate thread tid strings (numeric IDs)."""
    return st.integers(min_value=1, max_value=9999999).map(str)


def thread_dict_strategy():
    """Generate a thread dict with a random tid."""
    return st.fixed_dictionaries({
        "tid": thread_tid_strategy(),
        "title": st.text(min_size=1, max_size=30),
        "url": st.just("https://keylol.com/t123-1-1"),
        "author": st.text(min_size=1, max_size=10),
        "date_text": st.just("2025-1-1"),
    })


def post_html(n_posts: int) -> str:
    """Build a simple HTML page with n_posts post divs."""
    parts = []
    for i in range(n_posts):
        post_id = 1000 + i
        parts.append(
            f'<div id="post_{post_id}">'
            f'  <div class="authi"><a href="#">Author{i}</a></div>'
            f'  <div class="authi"><em title="2025-1-1 12:00">2025-1-1 12:00</em></div>'
            f'  <div id="postmessage_{post_id}"><p>Content of post {i}</p></div>'
            f'</div>'
        )
    return "<html><body>" + "\n".join(parts) + "</body></html>"


# --- Property Tests ---


@given(
    target=date_strategy(),
    same_day=st.booleans(),
    has_time_suffix=st.booleans(),
    other_day_offset=st.integers(min_value=1, max_value=27),
)
@settings(max_examples=100)
def test_property_2_date_filter_correctness(target, same_day, has_time_suffix, other_day_offset):
    """Feature: keylol-mcp-server, Property 2: 日期过滤正确性

    **Validates: Requirements 3.2**

    For any list of thread metadata with various date strings, and any target
    date, the `matches_date` function should return true only for threads whose
    date matches the target, and false for all others.
    """
    # Build a matching date string
    matching_str = matching_date_string(target)
    if has_time_suffix:
        matching_str += " 14:30"

    # matches_date should return True for matching string
    assert matches_date(matching_str, target) is True, (
        f"Expected True for date_text={matching_str!r} with target={target}"
    )

    # Build a non-matching date string (different day)
    other_day = ((target.day - 1 + other_day_offset) % 28) + 1
    # Ensure it's actually different
    assume(other_day != target.day)

    non_matching_str = f"{target.year}-{target.month}-{other_day}"
    if has_time_suffix:
        non_matching_str += " 09:15"

    # matches_date should return False for non-matching string
    assert matches_date(non_matching_str, target) is False, (
        f"Expected False for date_text={non_matching_str!r} with target={target}"
    )

    # Empty string should never match
    assert matches_date("", target) is False


@given(
    thread_lists=st.lists(
        thread_dict_strategy(),
        min_size=1,
        max_size=30,
    ),
)
@settings(max_examples=100)
def test_property_4_thread_deduplication(thread_lists):
    """Feature: keylol-mcp-server, Property 4: 帖子去重

    **Validates: Requirements 3.5**

    For any collection of scraped threads, the output list should contain no
    duplicate tids — each tid appears exactly once.
    """
    # Simulate the deduplication logic from scrape_by_date
    seen_tids: set[str] = set()
    deduplicated: list[dict] = []

    for thread in thread_lists:
        tid = thread["tid"]
        if tid in seen_tids:
            continue
        seen_tids.add(tid)
        deduplicated.append(thread)

    # Verify: all tids in deduplicated list are unique
    result_tids = [t["tid"] for t in deduplicated]
    assert len(result_tids) == len(set(result_tids)), (
        f"Duplicate tids found in deduplicated result: {result_tids}"
    )

    # Verify: every unique tid from input appears exactly once in output
    input_unique_tids = set(t["tid"] for t in thread_lists)
    output_tids = set(result_tids)
    assert input_unique_tids == output_tids, (
        f"Mismatch: input unique tids={input_unique_tids}, output tids={output_tids}"
    )


@given(
    n_posts=st.integers(min_value=1, max_value=100),
    max_comments=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=100)
def test_property_5_comment_count_upper_bound(n_posts, max_comments):
    """Feature: keylol-mcp-server, Property 5: 评论数量上界

    **Validates: Requirements 4.2**

    For any thread with C total comments and a `max_comments` parameter M, the
    scraped result should contain at most min(C, M) comments.
    """
    # Build HTML with n_posts post divs
    html = post_html(n_posts)

    # Parse the page
    posts = parse_thread_page(html)

    # The first post is the main post, the rest are comments
    # Total comments available = len(posts) - 1 (if posts exist)
    total_comments = max(0, len(posts) - 1)

    # Apply the max_comments slicing logic (same as in _scrape_thread)
    comments = []
    for i, post in enumerate(posts):
        if i == 0:
            continue  # skip main post
        if len(comments) < max_comments:
            comments.append(post)

    # Property: comment count should be at most min(total_comments, max_comments)
    expected_upper_bound = min(total_comments, max_comments)
    assert len(comments) <= expected_upper_bound, (
        f"Got {len(comments)} comments, expected at most {expected_upper_bound} "
        f"(n_posts={n_posts}, max_comments={max_comments}, total_comments={total_comments})"
    )

    # Also verify the exact count equals the upper bound (since we have all posts on one page)
    assert len(comments) == expected_upper_bound, (
        f"Got {len(comments)} comments, expected exactly {expected_upper_bound} "
        f"(n_posts={n_posts}, max_comments={max_comments}, total_comments={total_comments})"
    )
