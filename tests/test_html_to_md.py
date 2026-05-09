"""Property-based tests for html_to_md module."""

import re

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from keylol_mcp.html_to_md import convert


# --- Strategies ---

def relative_path_strategy():
    """Generate plausible relative URL paths (no leading http)."""
    segments = st.from_regex(r"[a-z0-9_\-]+", fullmatch=True)
    path = st.lists(segments, min_size=1, max_size=4).map("/".join)
    # Optionally add query string
    query = st.one_of(
        st.just(""),
        st.from_regex(r"\?[a-z]+=\d+", fullmatch=True),
    )
    return st.tuples(path, query).map(lambda t: t[0] + t[1])


def html_with_relative_urls():
    """Generate HTML snippets containing relative href/src attributes."""
    rel_path = relative_path_strategy()
    link_text = st.from_regex(r"[A-Za-z0-9 ]{1,20}", fullmatch=True)

    @st.composite
    def build(draw):
        elements = []
        # Generate 1-3 elements with relative URLs
        n = draw(st.integers(min_value=1, max_value=3))
        paths_used = []
        for _ in range(n):
            path = draw(rel_path)
            paths_used.append(path)
            tag_type = draw(st.sampled_from(["a", "img"]))
            if tag_type == "a":
                text = draw(link_text)
                elements.append(f'<a href="{path}">{text}</a>')
            else:
                elements.append(f'<img src="{path}">')
        html = "<p>" + " ".join(elements) + "</p>"
        return html, paths_used

    return build()


def html_with_discuz_system_elements():
    """Generate HTML containing Discuz system elements that should be removed."""

    @st.composite
    def build(draw):
        elements = []
        has_smilieid = draw(st.booleans())
        has_aimg_tip = draw(st.booleans())

        # Ensure at least one system element is present
        assume(has_smilieid or has_aimg_tip)

        if has_smilieid:
            smilie_id = draw(st.integers(min_value=1, max_value=999))
            elements.append(
                f'<img smilieid="{smilie_id}" src="static/image/smiley/default/smile.gif" />'
            )

        if has_aimg_tip:
            tip_text = draw(st.from_regex(r"[A-Za-z0-9 ]{1,20}", fullmatch=True))
            elements.append(
                f'<div class="aimg_tip">{tip_text}</div>'
            )

        # Add some normal content so the output isn't empty
        normal_text = draw(st.from_regex(r"[A-Za-z0-9 ]{5,30}", fullmatch=True))
        elements.append(f"<p>{normal_text}</p>")

        # Shuffle to make order non-deterministic
        order = draw(st.permutations(range(len(elements))))
        html = "".join(elements[i] for i in order)
        return html, has_smilieid, has_aimg_tip

    return build()


# --- Property Tests ---


@given(data=html_with_relative_urls())
@settings(max_examples=100)
def test_property_8_relative_url_resolution(data):
    """Feature: keylol-mcp-server, Property 8: 相对 URL 解析

    **Validates: Requirements 5.2**

    For any HTML containing relative URLs (href or src attributes not starting
    with http), the converter output should contain only absolute URLs prefixed
    with the base URL.
    """
    html, paths_used = data
    base_url = "https://keylol.com"
    result = convert(html, base_url=base_url)

    # Extract all URLs from the markdown output (both link and image syntax)
    # Markdown links: [text](url) and images: ![alt](url)
    # html2text may wrap URLs in angle brackets: [text](<url>)
    urls_in_output = re.findall(r'\[.*?\]\(<?([^>)\s]+)>?\)', result)

    # All extracted URLs should be absolute (start with http)
    for url in urls_in_output:
        assert url.startswith("http"), (
            f"Found non-absolute URL in output: {url!r}\n"
            f"Input HTML: {html!r}\n"
            f"Output: {result!r}"
        )

    # Each relative path should have been resolved to include the base URL
    for path in paths_used:
        expected_url = f"{base_url}/{path.lstrip('/')}"
        assert expected_url in result, (
            f"Expected resolved URL {expected_url!r} not found in output.\n"
            f"Input HTML: {html!r}\n"
            f"Output: {result!r}"
        )


@given(data=html_with_discuz_system_elements())
@settings(max_examples=100)
def test_property_9_system_elements_removal(data):
    """Feature: keylol-mcp-server, Property 9: 系统元素移除

    **Validates: Requirements 5.3**

    For any HTML containing Discuz system elements (smilieid images, aimg_tip
    divs, signature blocks), the converter output should not contain these
    elements.
    """
    html, has_smilieid, has_aimg_tip = data
    result = convert(html)

    # smilieid images should be completely removed
    if has_smilieid:
        assert "smilieid" not in result, (
            f"smilieid text found in output.\n"
            f"Input HTML: {html!r}\n"
            f"Output: {result!r}"
        )

    # aimg_tip divs should be completely removed
    if has_aimg_tip:
        assert "aimg_tip" not in result, (
            f"aimg_tip text found in output.\n"
            f"Input HTML: {html!r}\n"
            f"Output: {result!r}"
        )
