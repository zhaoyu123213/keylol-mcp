"""Keylol MCP Server 输出格式化模块

将 ThreadData 转换为 Markdown（带 YAML front-matter）或 JSON 格式。
"""

import json

from keylol_mcp.models import ThreadData


def to_markdown(thread: ThreadData) -> str:
    """生成带 YAML front-matter 的 Markdown 文件内容。

    输出格式：
    ---
    title: "帖子标题"
    author: "作者名"
    date: "发帖日期"
    url: "帖子链接"
    tid: "帖子ID"
    scraped_at: "采集时间"
    ---

    # 帖子标题

    {正文内容}

    ---

    ## 评论 (N 条)

    ### #1 评论者　日期
    {评论内容}
    """
    meta = thread.meta

    # YAML front-matter
    lines = [
        "---",
        f'title: "{meta.title}"',
        f'author: "{meta.author}"',
        f'date: "{meta.date_text}"',
        f'url: "{meta.url}"',
        f'tid: "{meta.tid}"',
        f'scraped_at: "{thread.scraped_at}"',
        "---",
        "",
        f"# {meta.title}",
        "",
    ]

    # 主楼内容
    if thread.main_post and thread.main_post.content_md:
        lines.append(thread.main_post.content_md)
        lines.append("")

    # 评论区
    if thread.comments:
        lines.append("---")
        lines.append("")
        lines.append(f"## 评论 ({len(thread.comments)} 条)")
        lines.append("")

        for i, comment in enumerate(thread.comments, 1):
            lines.append(f"### #{i} {comment.author}\u3000{comment.date_text}")
            lines.append("")
            if comment.content_md:
                lines.append(comment.content_md)
                lines.append("")

    return "\n".join(lines)


def to_json(thread: ThreadData) -> str:
    """生成 JSON 字符串。

    输出包含 meta、main_post、comments 三个顶层字段。
    """
    data = {
        "meta": {
            "tid": thread.meta.tid,
            "title": thread.meta.title,
            "url": thread.meta.url,
            "author": thread.meta.author,
            "date_text": thread.meta.date_text,
            "scraped_at": thread.scraped_at,
        },
        "main_post": None,
        "comments": [],
    }

    if thread.main_post:
        data["main_post"] = {
            "author": thread.main_post.author,
            "date_text": thread.main_post.date_text,
            "content_md": thread.main_post.content_md,
        }

    for comment in thread.comments:
        data["comments"].append(
            {
                "author": comment.author,
                "date_text": comment.date_text,
                "content_md": comment.content_md,
            }
        )

    return json.dumps(data, ensure_ascii=False, indent=2)
