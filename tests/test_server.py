"""Tests for MCP server module."""

import os
import json
import tempfile
from unittest.mock import patch, AsyncMock
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from keylol_mcp.server import scrape_keylol, _get_cookie, _write_thread_file
from keylol_mcp.models import PostData, ThreadMeta, ThreadData


# --- Fixtures ---


def make_thread(tid="12345", title="Test Thread", date_text="2026-4-9 12:00"):
    """Create a simple ThreadData for testing."""
    return ThreadData(
        meta=ThreadMeta(
            tid=tid,
            title=title,
            url=f"https://keylol.com/t{tid}-1-1",
            author="TestAuthor",
            date_text=date_text,
        ),
        main_post=PostData(
            author="TestAuthor",
            date_text=date_text,
            content_html="<p>Hello world</p>",
            content_md="Hello world",
        ),
        comments=[
            PostData(
                author="Commenter",
                date_text="2026-4-9 13:00",
                content_html="<p>Nice post</p>",
                content_md="Nice post",
            )
        ],
        scraped_at="2026-04-09 14:00:00",
    )


# --- Strategies ---

tid_strategy = st.from_regex(r"[0-9]{4,8}", fullmatch=True)
date_strategy = st.from_regex(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", fullmatch=True)


# --- Unit Tests ---


def test_get_cookie_missing():
    """Cookie 未设置时应抛出 ValueError"""
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("KEYLOL_COOKIE", None)
        with pytest.raises(ValueError, match="KEYLOL_COOKIE"):
            _get_cookie()


def test_get_cookie_present():
    """Cookie 设置时应正常返回"""
    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test_cookie_value"}):
        assert _get_cookie() == "test_cookie_value"


def test_write_thread_file_markdown():
    """Markdown 格式文件写入"""
    thread = make_thread()
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = _write_thread_file(thread, "markdown", Path(tmpdir))
        assert filepath.endswith(".md")
        assert "12345" in filepath
        content = Path(filepath).read_text(encoding="utf-8")
        assert "---" in content
        assert "Test Thread" in content


def test_write_thread_file_json():
    """JSON 格式文件写入"""
    thread = make_thread()
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = _write_thread_file(thread, "json", Path(tmpdir))
        assert filepath.endswith(".json")
        content = Path(filepath).read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["meta"]["tid"] == "12345"


@pytest.mark.asyncio
async def test_scrape_keylol_no_cookie():
    """未设置 cookie 时应返回错误"""
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("KEYLOL_COOKIE", None)
        result = await scrape_keylol()
        assert result["success"] is False
        assert "KEYLOL_COOKIE" in result["error"]


@pytest.mark.asyncio
async def test_scrape_keylol_invalid_format():
    """无效 format 参数应返回错误"""
    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test"}):
        result = await scrape_keylol(format="xml")
        assert result["success"] is False
        assert "Invalid format" in result["error"]


@pytest.mark.asyncio
async def test_scrape_keylol_invalid_date():
    """无效日期格式应返回错误"""
    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test"}):
        result = await scrape_keylol(date="not-a-date")
        assert result["success"] is False
        assert "Invalid date format" in result["error"]


@pytest.mark.asyncio
async def test_scrape_keylol_tid_mode():
    """tid 模式应调用 scrape_by_tid"""
    thread = make_thread(tid="99999")

    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test"}):
        with patch("keylol_mcp.server.scrape_by_tid", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = thread
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await scrape_keylol(tid="99999", output_dir=tmpdir)

                assert result["success"] is True
                assert result["threads_scraped"] == 1
                assert len(result["files_written"]) == 1
                mock_scrape.assert_called_once()
                # Verify tid was passed, date was ignored
                call_kwargs = mock_scrape.call_args[1]
                assert call_kwargs["tid"] == "99999"


@pytest.mark.asyncio
async def test_scrape_keylol_tid_ignores_date():
    """Property 1: 当 tid 和 date 都提供时，应只使用 tid 模式"""
    thread = make_thread(tid="88888")

    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test"}):
        with patch("keylol_mcp.server.scrape_by_tid", new_callable=AsyncMock) as mock_tid:
            with patch("keylol_mcp.server.scrape_by_date", new_callable=AsyncMock) as mock_date:
                mock_tid.return_value = thread
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = await scrape_keylol(
                        tid="88888", date="2026-01-01", output_dir=tmpdir
                    )

                    assert result["success"] is True
                    mock_tid.assert_called_once()
                    mock_date.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_keylol_date_mode():
    """date 模式应调用 scrape_by_date"""
    threads = [make_thread(tid="11111"), make_thread(tid="22222")]

    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test"}):
        with patch("keylol_mcp.server.scrape_by_date", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = threads
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await scrape_keylol(date="2026-04-09", output_dir=tmpdir)

                assert result["success"] is True
                assert result["threads_scraped"] == 2
                assert len(result["files_written"]) == 2


# --- Property Tests ---


@given(
    tid=tid_strategy,
    date_str=date_strategy,
)
@settings(max_examples=100)
def test_property_1_tid_priority(tid, date_str):
    """Feature: keylol-mcp-server, Property 1: tid 参数优先级

    **Validates: Requirements 2.3**

    For any invocation where both `tid` and `date` are provided, the scraper
    should only fetch the single thread identified by `tid` and never perform
    date-based list scraping.
    """
    import asyncio

    thread = make_thread(tid=tid)

    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test"}):
        with patch("keylol_mcp.server.scrape_by_tid", new_callable=AsyncMock) as mock_tid:
            with patch("keylol_mcp.server.scrape_by_date", new_callable=AsyncMock) as mock_date:
                mock_tid.return_value = thread
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = asyncio.run(
                        scrape_keylol(tid=tid, date=date_str, output_dir=tmpdir)
                    )

                    # tid mode should be used
                    mock_tid.assert_called_once()
                    # date mode should NOT be called
                    mock_date.assert_not_called()
                    # Result should be successful
                    assert result["success"] is True


@given(
    n_threads=st.integers(min_value=0, max_value=5),
    fmt=st.sampled_from(["json", "markdown"]),
)
@settings(max_examples=100)
def test_property_12_output_summary_correctness(n_threads, fmt):
    """Feature: keylol-mcp-server, Property 12: 输出摘要正确性

    **Validates: Requirements 6.4, 6.5**

    For any scrape operation that processes N threads and writes files, the
    returned summary should report `threads_scraped` equal to N,
    `files_written` containing exactly N file paths, and each path matching
    the `{date}_{tid}.{ext}` pattern.
    """
    import asyncio
    import re

    threads = [make_thread(tid=str(10000 + i)) for i in range(n_threads)]

    with patch.dict(os.environ, {"KEYLOL_COOKIE": "test"}):
        with patch("keylol_mcp.server.scrape_by_date", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = threads
            with tempfile.TemporaryDirectory() as tmpdir:
                result = asyncio.run(
                    scrape_keylol(date="2026-04-09", format=fmt, output_dir=tmpdir)
                )

                assert result["success"] is True
                assert result["threads_scraped"] == n_threads
                assert len(result["files_written"]) == n_threads

                ext = "md" if fmt == "markdown" else "json"
                pattern = re.compile(r"\d{4}-\d{2}-\d{2}_\d+\." + ext + "$")
                for filepath in result["files_written"]:
                    assert pattern.search(filepath), (
                        f"File path '{filepath}' doesn't match expected pattern"
                    )
