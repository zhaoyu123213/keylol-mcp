"""Keylol MCP Server 数据模型"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PostData:
    """单个楼层数据"""

    author: str
    date_text: str
    content_html: str
    content_md: str = ""  # 转换后的 Markdown


@dataclass
class ThreadMeta:
    """帖子元信息"""

    tid: str
    title: str
    url: str
    author: str
    date_text: str


@dataclass
class ThreadData:
    """完整帖子数据"""

    meta: ThreadMeta
    main_post: PostData | None
    comments: list[PostData] = field(default_factory=list)
    scraped_at: str = ""  # ISO 格式时间戳

    def __post_init__(self):
        if not self.scraped_at:
            self.scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
