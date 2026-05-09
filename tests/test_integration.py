"""Integration tests for the full scrape pipeline with mocked HTTP."""

import os
import json
import tempfile
from unittest.mock import patch, AsyncMock
from pathlib import Path

import pytest

from keylol_mcp.server import scrape_keylol
from keylol_mcp.models import PostData, ThreadMeta, ThreadData


# --- Mock HTML fixtures ---

MOCK_LIST_HTML = """
<html><body>
<table id="threadlisttableid">
<tbody id="normalthread_100001">
  <tr>
    <td class="common"><a href="t100001-1-1" class="s xst">Bundle Post 1</a></td>
    <td class="by"><cite><a>Author1</a></cite><em><span title="2026-4-9 10:00">2026-4-9</span></em></td>
    <td class="by"><em>2026-4-9</em></td>
  </tr>
</tbody>
<tbody id="normalthread_100002">
  <tr>
    <td class="common"><a href="t100002-1-1" class="s xst">Bundle Post 2</a></td>
    <td class="by"><cite><a>Author2</a></cite><em><span title="2026-4-9 11:00">2026-4-9</span></em></td>
    <td class="by"><em>2026-4-9</em></td>
  </tr>
</tbody>
<tbody id="normalthread_100003">
  <tr>
    <td class="common"><a href="t100003-1-1" class="s xst">Old Post</a></td>
    <td class="by"><cite><a>Author3</a></cite><em><span title="2026-4-8 09:00">2026-4-8</span></em></td>
    <td class="by"><em>2026-4-8</em></td>
  </tr>
</tbody>
</table>
</body></html>
"""

MOCK_THREAD_HTML = """
<html><body>
<h1 id="thread_subject">Test Thread Title</h1>
<div id="post_1001">
  <div class="authi"><a href="#">MainAuthor</a></div>
  <div class="authi"><em title="2026-4-9 10:00">2026-4-9 10:00</em></div>
  <div id="postmessage_1001"><p>This is the main post content with a <a href="https://store.steampowered.com/app/12345">game link</a>.</p></div>
</div>
<div id="post_1002">
  <div class="authi"><a href="#">Commenter1</a></div>
  <div class="authi"><em title="2026-4-9 10:30">2026-4-9 10:30</em></div>
  <div id="postmessage_1002"><p>Great bundle!</p></div>
</div>
<div id="post_1003">
  <div class="authi"><a href="#">Commenter2</a></div>
  <div class="authi"><em title="2026-4-9 11:00">2026-4-9 11:00</em></div>
  <div id="postmessage_1003"><p>Not worth it.</p></div>
</div>
</body></html>
"""


def make_mock_response(html: str):
    """Create a mock httpx response."""
    mock_resp = AsyncMock()
    mock_resp.text = html
    mock_resp.raise_for_status = lambda: None
    return mock_resp


# --- Integration Tests ---


@pytest.mark.asyncio
async def test_full_pipeline_date_mode():
    """Integration: full pipeline from date-based scrape to file output."""
    import httpx

    call_count = {"n": 0}

    async def mock_get(url, **kwargs):
        call_count["n"] += 1
        if "forumdisplay" in url:
            return make_mock_response(MOCK_LIST_HTML)
        else:
            return make_mock_response(MOCK_THREAD_HTML)

    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test_cookie"}):
        with patch("keylol_mcp.scraper.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await scrape_keylol(
                    date="2026-04-09",
                    fid=319,
                    max_pages=1,
                    max_comments=5,
                    format="markdown",
                    output_dir=tmpdir,
                    request_delay=0,
                )

                assert result["success"] is True
                assert result["threads_scraped"] == 2  # Only 2 match date 2026-4-9
                assert len(result["files_written"]) == 2
                assert result["errors"] == []

                # Verify files exist and have content
                for filepath in result["files_written"]:
                    p = Path(filepath)
                    assert p.exists()
                    content = p.read_text(encoding="utf-8")
                    assert "---" in content  # YAML front-matter
                    assert "title:" in content


@pytest.mark.asyncio
async def test_full_pipeline_tid_mode():
    """Integration: full pipeline for single thread by tid."""
    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test_cookie"}):
        with patch("keylol_mcp.scraper.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=make_mock_response(MOCK_THREAD_HTML))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await scrape_keylol(
                    tid="100001",
                    format="json",
                    output_dir=tmpdir,
                    request_delay=0,
                )

                assert result["success"] is True
                assert result["threads_scraped"] == 1
                assert len(result["files_written"]) == 1

                # Verify JSON output
                filepath = result["files_written"][0]
                assert filepath.endswith(".json")
                content = Path(filepath).read_text(encoding="utf-8")
                data = json.loads(content)
                assert data["meta"]["tid"] == "100001"
                assert data["main_post"] is not None
                assert "game link" in data["main_post"]["content_md"]


@pytest.mark.asyncio
async def test_property_13_error_tolerance():
    """Feature: keylol-mcp-server, Property 13: 错误容忍

    **Validates: Requirements 7.2**

    For any batch of threads where some fail to fetch, the scraper should
    still return results for all successfully fetched threads.
    """
    call_count = {"n": 0}

    async def mock_get_with_failures(url, **kwargs):
        call_count["n"] += 1
        if "forumdisplay" in url:
            return make_mock_response(MOCK_LIST_HTML)
        # First thread succeeds, second fails
        if "t100001" in url:
            return make_mock_response(MOCK_THREAD_HTML)
        if "t100002" in url:
            # Simulate HTTP error
            import httpx
            mock_resp = AsyncMock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "503 Service Unavailable",
                request=AsyncMock(),
                response=AsyncMock(status_code=503),
            )
            return mock_resp
        return make_mock_response(MOCK_THREAD_HTML)

    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test_cookie"}):
        with patch("keylol_mcp.scraper.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get_with_failures
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await scrape_keylol(
                    date="2026-04-09",
                    fid=319,
                    max_pages=1,
                    max_comments=5,
                    format="markdown",
                    output_dir=tmpdir,
                    request_delay=0,
                )

                # Should still succeed overall
                assert result["success"] is True
                # At least one thread should have been scraped successfully
                assert result["threads_scraped"] >= 1
                # Files should be written for successful threads
                assert len(result["files_written"]) >= 1
