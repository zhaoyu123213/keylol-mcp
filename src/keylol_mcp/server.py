"""Keylol MCP Server - 通过 MCP 协议采集其乐论坛帖子数据"""

import os
import re
import logging
from datetime import date, datetime
from pathlib import Path

from fastmcp import FastMCP

from keylol_mcp.scraper import scrape_by_date, scrape_by_tid, scrape_latest_threads
from keylol_mcp.formatter import to_markdown, to_json
from keylol_mcp.models import ThreadData

log = logging.getLogger("keylol-mcp")

mcp = FastMCP("Keylol Scraper")


def _get_cookie() -> str:
    """获取 KEYLOL_COOKIE 环境变量"""
    cookie = os.environ.get("KEYLOL_COOKIE", "")
    if not cookie:
        raise ValueError("KEYLOL_COOKIE environment variable not set")
    return cookie


def _write_thread_file(thread: ThreadData, fmt: str, output_dir: Path) -> str:
    """将单个帖子写入文件，返回文件路径"""
    # 从帖子日期提取日期部分用于文件名
    date_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", thread.meta.date_text)
    if date_match:
        file_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    else:
        file_date = datetime.now().strftime("%Y-%m-%d")

    ext = "md" if fmt == "markdown" else "json"
    filename = f"{file_date}_{thread.meta.tid}.{ext}"
    filepath = output_dir / filename

    if fmt == "markdown":
        content = to_markdown(thread)
    else:
        content = to_json(thread)

    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


@mcp.tool()
async def scrape_keylol(
    date: str = "",
    tid: str = "",
    fid: int = 271,
    mode: str = "",
    max_pages: int = 3,
    max_comments: int = 50,
    include_comments: bool = True,
    format: str = "markdown",
    output_dir: str = "./keylol_output",
    request_delay: float = 0.6,
) -> dict:
    """采集 Keylol 论坛帖子数据。

    支持三种模式：
    - 按日期采集：指定 date 参数，爬取该日期在指定板块的所有帖子
    - 按帖子ID采集：指定 tid 参数，只爬取该帖子（忽略 date）
    - 最新发表：指定 mode="newthread"，爬取全站最新发表的帖子

    Args:
        date: 采集日期，格式 YYYY-MM-DD，默认今天
        tid: 指定帖子 ID，如果提供则只爬这一个帖子（忽略 date 参数）
        fid: 板块 ID，默认 319（慈善包板块）
        mode: 采集模式，"newthread" 表示爬取全站最新发表页面，留空则按板块采集
        max_pages: 列表翻页上限，默认 3
        max_comments: 每帖最多抓多少评论，默认 50
        include_comments: 是否需要评论，默认 true
        format: 输出格式，"json" 或 "markdown"，默认 "markdown"
        output_dir: 文件保存目录，默认 "./keylol_output"
        request_delay: 请求间隔秒数，默认 0.6
    """
    # 验证 cookie
    try:
        cookie = _get_cookie()
    except ValueError as e:
        return {"success": False, "error": str(e), "threads_scraped": 0, "files_written": [], "errors": []}

    # 验证 format 参数
    if format not in ("json", "markdown"):
        return {
            "success": False,
            "error": f"Invalid format '{format}', must be 'json' or 'markdown'",
            "threads_scraped": 0,
            "files_written": [],
            "errors": [],
        }

    # 创建输出目录（按来源自动分子目录）
    out_path = Path(output_dir)
    if tid:
        # 单帖模式：output_dir/tid/
        out_path = out_path / "tid"
    elif mode == "newthread":
        # 最新发表模式：output_dir/newthread/YYYY-MM-DD/
        if date:
            out_path = out_path / "newthread" / date
        else:
            from datetime import date as date_cls
            out_path = out_path / "newthread" / date_cls.today().isoformat()
    else:
        # 板块模式：output_dir/f{fid}/YYYY-MM-DD/
        if date:
            out_path = out_path / f"f{fid}" / date
        else:
            from datetime import date as date_cls
            out_path = out_path / f"f{fid}" / date_cls.today().isoformat()

    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"success": False, "error": f"Cannot create output directory: {e}", "threads_scraped": 0, "files_written": [], "errors": []}

    threads: list[ThreadData] = []
    errors: list[dict] = []

    if tid:
        # 按 tid 模式
        try:
            thread_data = await scrape_by_tid(
                cookie=cookie,
                tid=tid,
                max_comments=max_comments,
                include_comments=include_comments,
                request_delay=request_delay,
            )
            threads.append(thread_data)
        except Exception as e:
            errors.append({"tid": tid, "error": str(e)})
    elif mode == "newthread":
        # 最新发表模式：爬取全站最新帖子
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid date format '{date}', expected YYYY-MM-DD",
                    "threads_scraped": 0,
                    "files_written": [],
                    "errors": [],
                }
        else:
            from datetime import date as date_cls
            target_date = date_cls.today()

        try:
            threads = await scrape_latest_threads(
                cookie=cookie,
                max_pages=max_pages,
                max_comments=max_comments,
                include_comments=include_comments,
                request_delay=request_delay,
                target_date=target_date,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "threads_scraped": 0, "files_written": [], "errors": []}
    else:
        # 按板块+日期模式
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid date format '{date}', expected YYYY-MM-DD",
                    "threads_scraped": 0,
                    "files_written": [],
                    "errors": [],
                }
        else:
            from datetime import date as date_cls
            target_date = date_cls.today()

        try:
            threads = await scrape_by_date(
                cookie=cookie,
                fid=fid,
                target_date=target_date,
                max_pages=max_pages,
                max_comments=max_comments,
                include_comments=include_comments,
                request_delay=request_delay,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "threads_scraped": 0, "files_written": [], "errors": []}

    # 写入文件
    files_written: list[str] = []
    for thread in threads:
        try:
            filepath = _write_thread_file(thread, format, out_path)
            files_written.append(filepath)
        except Exception as e:
            errors.append({"tid": thread.meta.tid, "error": f"File write failed: {e}"})

    return {
        "success": True,
        "threads_scraped": len(threads),
        "files_written": files_written,
        "errors": errors,
    }


def main():
    """MCP Server 入口"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
