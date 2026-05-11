"""Keylol 慈善包板块异步爬虫"""

import re
import asyncio
import logging
from datetime import date, timedelta

import httpx
from bs4 import BeautifulSoup

from keylol_mcp.models import PostData, ThreadMeta, ThreadData
from keylol_mcp.html_to_md import convert

BASE_URL = "https://keylol.com"

log = logging.getLogger("keylol")


# ---------------------------------------------------------------------------
# HTML 解析函数（移植自同步版本）
# ---------------------------------------------------------------------------


def parse_guide_newthread_list(html: str) -> list[dict]:
    """从"最新发表"页面 (forum.php?mod=guide&view=newthread) 解析帖子列表。

    该页面使用 Discuz 的 guide 模块，HTML 结构与板块列表页略有不同：
    - 帖子在 <table class="dt"> 内，或直接在 tbody[id^="normalthread_"] 中
    - 多一个"板块"列
    """
    soup = BeautifulSoup(html, "html.parser")
    threads = []

    # 尝试两种选择器：guide 页面可能用不同的容器
    tbodies = soup.select('tbody[id^="normalthread_"]')
    if not tbodies:
        # 备选：guide 页面有时用 <tr> 直接在 table 里
        tbodies = []

    for tbody in tbodies:
        try:
            title_el = tbody.select_one("a.s.xst") or tbody.select_one("th a.xst") or tbody.select_one("a.xst")
            if not title_el:
                # guide 页面的链接可能没有 .s 类
                title_el = tbody.select_one('a[href*="thread-"]') or tbody.select_one('a[href^="t"]')
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"

            tid_match = re.search(
                r"(?:thread-|(?:^|/)t)(\d+)", href
            ) or re.search(r"\bt(\d+)-", href)
            tid = tid_match.group(1) if tid_match else ""

            author_el = tbody.select_one("td.by cite a") or tbody.select_one(".by a")
            author = author_el.get_text(strip=True) if author_el else ""

            # 提取日期 - guide 页面结构：td.by[0]=板块, td.by[1]=作者+日期, td.by[2]=最后回复
            by_cells = tbody.select("td.by")
            date_text = ""
            if len(by_cells) >= 2:
                # 日期在第二个 td.by 的 em > span[title] 里
                second_by = by_cells[1]
                span = second_by.select_one("em span[title]")
                if span:
                    date_text = span.get("title", "")
                else:
                    em = second_by.select_one("em")
                    if em:
                        date_text = em.get_text(strip=True)
                # 作者在第二个 td.by 的 cite > a 里
                author_el2 = second_by.select_one("cite a")
                if author_el2:
                    author = author_el2.get_text(strip=True)
            elif by_cells:
                first_by = by_cells[0]
                span = first_by.select_one("em span[title]")
                if span:
                    date_text = span.get("title", "")
                else:
                    em = first_by.select_one("em")
                    if em:
                        date_text = em.get_text(strip=True)

            # 提取板块名 - guide 页面第一个 td.by 里的链接
            forum_el = None
            if by_cells:
                forum_el = by_cells[0].select_one("a[href*='f']")
            forum_name = forum_el.get_text(strip=True) if forum_el else ""

            if not tid:
                continue

            threads.append(
                {
                    "tid": tid,
                    "title": title,
                    "url": url,
                    "author": author,
                    "date_text": date_text,
                    "forum_name": forum_name,
                }
            )
        except Exception:
            continue

    return threads


def parse_thread_list(html: str) -> list[dict]:
    """从板块列表页解析帖子元信息"""
    soup = BeautifulSoup(html, "html.parser")
    threads = []

    for tbody in soup.select('#threadlisttableid > tbody[id^="normalthread_"]'):
        try:
            title_el = tbody.select_one("a.s.xst")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"

            tid_match = re.search(
                r"(?:thread-|(?:^|/)t)(\d+)", href
            ) or re.search(r"\bt(\d+)-", href)
            tid = tid_match.group(1) if tid_match else ""

            author_el = tbody.select_one("td.by cite a") or tbody.select_one(".by a")
            author = author_el.get_text(strip=True) if author_el else ""

            by_cells = tbody.select("td.by")
            date_text = ""
            if by_cells:
                first_by = by_cells[0]
                span = first_by.select_one("em span[title]")
                if span:
                    date_text = span.get("title", "")
                else:
                    em = first_by.select_one("em")
                    if em:
                        date_text = em.get_text(strip=True)

            if not tid:
                continue

            threads.append(
                {
                    "tid": tid,
                    "title": title,
                    "url": url,
                    "author": author,
                    "date_text": date_text,
                }
            )
        except Exception:
            continue

    return threads


def matches_date(date_text: str, target: date) -> bool:
    """判断日期文本是否匹配目标日期"""
    if not date_text:
        return False

    target_str = f"{target.year}-{target.month}-{target.day}"

    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_text)
    if match:
        d = f"{match.group(1)}-{int(match.group(2))}-{int(match.group(3))}"
        return d == target_str

    today = date.today()
    if "昨天" in date_text and target == today - timedelta(days=1):
        return True
    if "前天" in date_text and target == today - timedelta(days=2):
        return True

    if target == today and re.search(r"分钟前|小时前|秒前", date_text):
        return True

    return False


def parse_thread_page(html: str) -> list[dict]:
    """解析帖子页面中的所有楼层"""
    soup = BeautifulSoup(html, "html.parser")
    posts = []

    for post_div in soup.select('[id^="post_"]'):
        content_el = post_div.select_one(
            '[id^="postmessage_"]'
        ) or post_div.select_one(".t_f")
        if not content_el:
            continue

        for tag in content_el.select(
            "script, style, .pstatus, .tip, .aimg_tip, "
            ".sign_inner, .bm_c, .locked, "
            "div.modact, div.pattl, div.rusession, "
            "div[id^='aimg_'], .a_pr, .a_pl"
        ):
            tag.decompose()

        for img in content_el.select("img"):
            src = img.get("src", "") or img.get("file", "")
            if any(
                x in src
                for x in ["/static/", "/template/", "forum.php", "member.php"]
            ):
                img.decompose()
                continue
            if any(
                x in src.lower()
                for x in [
                    "humblebundle.com/misc",
                    "humble-images",
                    "hb.imgix.net",
                    "/ad/",
                    "/ads/",
                    "/banner/",
                    "/promo/",
                    "keylol.com/sdo",
                    "keylol.com/static/image/common",
                ]
            ):
                img.decompose()

        for a_tag in content_el.select("a[href]"):
            href = a_tag.get("href", "").lower()
            if any(
                x in href
                for x in [
                    "promo.humblebundle.com",
                    "utm_campaign",
                    "utm_medium=paid",
                ]
            ):
                children = [
                    c
                    for c in a_tag.children
                    if c.name or (c.string and c.string.strip())
                ]
                if all(
                    getattr(c, "name", None) == "img"
                    for c in children
                    if hasattr(c, "name")
                ):
                    a_tag.decompose()

        author_el = post_div.select_one(".authi a") or post_div.select_one(".pi a")
        author = author_el.get_text(strip=True) if author_el else ""

        date_el = post_div.select_one(".authi em") or post_div.select_one(".pi em")
        date_text = ""
        if date_el:
            date_text = date_el.get("title", "") or date_el.get_text(strip=True)

        content_html = str(content_el)

        posts.append(
            {
                "author": author,
                "date_text": date_text,
                "content_html": content_html,
            }
        )

    return posts


def get_max_page(html: str) -> int:
    """获取帖子总页数"""
    soup = BeautifulSoup(html, "html.parser")
    last_link = soup.select_one(".pg a.last")
    if last_link:
        match = re.search(r"page=(\d+)", last_link.get("href", ""))
        if match:
            return int(match.group(1))

    max_p = 1
    for a in soup.select(".pg a"):
        try:
            num = int(a.get_text(strip=True))
            if num > max_p:
                max_p = num
        except ValueError:
            continue
    return max_p


# ---------------------------------------------------------------------------
# 异步爬虫核心
# ---------------------------------------------------------------------------


def _build_client(cookie: str) -> httpx.AsyncClient:
    """构建 httpx 异步客户端"""
    return httpx.AsyncClient(
        timeout=15.0,
        headers={
            "Cookie": cookie,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        },
        follow_redirects=True,
    )


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    """获取页面 HTML，失败返回 None"""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as e:
        log.warning("HTTP error fetching %s: %s", url, e)
        return None


async def _scrape_thread(
    client: httpx.AsyncClient,
    meta: ThreadMeta,
    max_comments: int,
    include_comments: bool,
    request_delay: float,
) -> ThreadData:
    """采集单个帖子的完整内容（含分页评论）"""
    thread_url = f"{BASE_URL}/t{meta.tid}-1-1"
    html = await _fetch_page(client, thread_url)

    if not html:
        # 返回只有 meta 的空数据
        return ThreadData(meta=meta, main_post=None, comments=[])

    posts = parse_thread_page(html)
    all_posts = list(posts)

    # 如果需要评论且有多页，继续翻页
    if include_comments and max_comments > 0:
        total_pages = get_max_page(html)
        for page in range(2, total_pages + 1):
            # 检查是否已经收集够评论（主楼占 1 个位置）
            if len(all_posts) - 1 >= max_comments:
                break

            await asyncio.sleep(request_delay)
            page_url = f"{BASE_URL}/t{meta.tid}-{page}-1"
            page_html = await _fetch_page(client, page_url)
            if not page_html:
                continue
            page_posts = parse_thread_page(page_html)
            all_posts.extend(page_posts)

    # 分离主楼和评论
    main_post = None
    comments: list[PostData] = []

    for i, post in enumerate(all_posts):
        post_data = PostData(
            author=post["author"],
            date_text=post["date_text"],
            content_html=post["content_html"],
            content_md=convert(post["content_html"]),
        )
        if i == 0:
            main_post = post_data
        else:
            if include_comments and len(comments) < max_comments:
                comments.append(post_data)

    return ThreadData(meta=meta, main_post=main_post, comments=comments)


async def scrape_by_date(
    cookie: str,
    fid: int,
    target_date: date,
    max_pages: int,
    max_comments: int,
    include_comments: bool,
    request_delay: float,
) -> list[ThreadData]:
    """按日期采集板块帖子列表并抓取内容"""
    results: list[ThreadData] = []
    seen_tids: set[str] = set()

    async with _build_client(cookie) as client:
        for page in range(1, max_pages + 1):
            list_url = (
                f"{BASE_URL}/forum.php?mod=forumdisplay&fid={fid}&page={page}"
            )

            await asyncio.sleep(request_delay) if page > 1 else None
            html = await _fetch_page(client, list_url)
            if not html:
                log.warning("Failed to fetch list page %d", page)
                break

            threads = parse_thread_list(html)
            matched = [t for t in threads if matches_date(t["date_text"], target_date)]

            # 如果本页没有匹配日期的帖子，停止翻页
            if not matched:
                break

            for t in matched:
                tid = t["tid"]
                if tid in seen_tids:
                    continue
                seen_tids.add(tid)

                meta = ThreadMeta(
                    tid=tid,
                    title=t["title"],
                    url=t["url"],
                    author=t["author"],
                    date_text=t["date_text"],
                )

                await asyncio.sleep(request_delay)
                try:
                    thread_data = await _scrape_thread(
                        client, meta, max_comments, include_comments, request_delay
                    )
                    results.append(thread_data)
                except Exception as e:
                    log.warning("Error scraping thread %s: %s", tid, e)
                    continue

    return results


async def scrape_by_tid(
    cookie: str,
    tid: str,
    max_comments: int,
    include_comments: bool,
    request_delay: float,
) -> ThreadData:
    """按帖子 ID 采集单个帖子"""
    meta = ThreadMeta(
        tid=tid,
        title="",
        url=f"{BASE_URL}/t{tid}-1-1",
        author="",
        date_text="",
    )

    async with _build_client(cookie) as client:
        thread_url = f"{BASE_URL}/t{tid}-1-1"
        html = await _fetch_page(client, thread_url)

        if not html:
            raise httpx.HTTPError(f"Failed to fetch thread {tid}")

        # 尝试从页面提取标题
        soup = BeautifulSoup(html, "html.parser")
        title_el = soup.select_one("#thread_subject") or soup.select_one("h1.ts")
        if title_el:
            meta.title = title_el.get_text(strip=True)

        # 提取主楼作者和日期
        posts = parse_thread_page(html)
        all_posts = list(posts)

        # 翻页采集评论
        if include_comments and max_comments > 0:
            total_pages = get_max_page(html)
            for page in range(2, total_pages + 1):
                if len(all_posts) - 1 >= max_comments:
                    break

                await asyncio.sleep(request_delay)
                page_url = f"{BASE_URL}/t{tid}-{page}-1"
                page_html = await _fetch_page(client, page_url)
                if not page_html:
                    continue
                page_posts = parse_thread_page(page_html)
                all_posts.extend(page_posts)

        # 分离主楼和评论
        main_post = None
        comments: list[PostData] = []

        for i, post in enumerate(all_posts):
            post_data = PostData(
                author=post["author"],
                date_text=post["date_text"],
                content_html=post["content_html"],
                content_md=convert(post["content_html"]),
            )
            if i == 0:
                main_post = post_data
                # 用主楼信息补充 meta
                if not meta.author:
                    meta.author = post_data.author
                if not meta.date_text:
                    meta.date_text = post_data.date_text
            else:
                if include_comments and len(comments) < max_comments:
                    comments.append(post_data)

        return ThreadData(meta=meta, main_post=main_post, comments=comments)


async def scrape_latest_threads(
    cookie: str,
    max_pages: int,
    max_comments: int,
    include_comments: bool,
    request_delay: float,
    target_date: date | None = None,
) -> list[ThreadData]:
    """采集"最新发表"页面的帖子列表并抓取内容。

    URL: https://keylol.com/forum.php?mod=guide&view=newthread
    该页面展示全站所有板块当天最新发表的帖子。

    Args:
        cookie: Keylol cookie
        max_pages: 列表翻页上限
        max_comments: 每帖最多抓多少评论
        include_comments: 是否需要评论
        request_delay: 请求间隔秒数
        target_date: 目标日期过滤，None 表示不过滤（抓取所有）
    """
    results: list[ThreadData] = []
    seen_tids: set[str] = set()

    async with _build_client(cookie) as client:
        for page in range(1, max_pages + 1):
            list_url = (
                f"{BASE_URL}/forum.php?mod=guide&view=newthread&page={page}"
            )

            if page > 1:
                await asyncio.sleep(request_delay)
            html = await _fetch_page(client, list_url)
            if not html:
                log.warning("Failed to fetch guide newthread page %d", page)
                break

            threads = parse_guide_newthread_list(html)

            if not threads:
                # 如果解析不到帖子，可能页面结构不同，尝试用板块列表解析器
                threads = parse_thread_list(html)

            if not threads:
                log.warning("No threads found on page %d", page)
                break

            # 如果指定了日期，过滤匹配的帖子
            if target_date:
                matched = [t for t in threads if matches_date(t["date_text"], target_date)]
                if not matched:
                    break
            else:
                matched = threads

            for t in matched:
                tid = t["tid"]
                if tid in seen_tids:
                    continue
                seen_tids.add(tid)

                meta = ThreadMeta(
                    tid=tid,
                    title=t["title"],
                    url=t["url"],
                    author=t["author"],
                    date_text=t["date_text"],
                )

                await asyncio.sleep(request_delay)
                try:
                    thread_data = await _scrape_thread(
                        client, meta, max_comments, include_comments, request_delay
                    )
                    results.append(thread_data)
                except Exception as e:
                    log.warning("Error scraping thread %s: %s", tid, e)
                    continue

    return results
