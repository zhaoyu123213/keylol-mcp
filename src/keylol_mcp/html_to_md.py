"""HTML 转 Markdown 工具，针对 Keylol (Discuz) 帖子优化"""

import html2text
import re

_converter = html2text.HTML2Text()
_converter.body_width = 0          # 不自动换行
_converter.protect_links = True
_converter.wrap_links = False
_converter.wrap_list_items = False
_converter.skip_internal_links = False
_converter.ignore_images = False
_converter.ignore_emphasis = False
_converter.single_line_break = True
_converter.unicode_snob = True


def convert(html: str, base_url: str = "https://keylol.com") -> str:
    """将帖子 HTML 转为干净的 Markdown"""
    if not html:
        return ""

    # 预处理：修正 Discuz 特有的标签
    # file 属性的图片 → 用 file 作为 src（通常是原图）
    html = re.sub(r'<img([^>]*)\bfile="([^"]+)"([^>]*)>',
                  lambda m: f'<img{m.group(1)} src="{m.group(2)}"{m.group(3)}>', html)

    # zoomfile 属性
    html = re.sub(r'<img([^>]*)\bzoomfile="([^"]+)"([^>]*)>',
                  lambda m: f'<img{m.group(1)} src="{m.group(2)}"{m.group(3)}>' if 'src=' not in m.group(0) else m.group(0), html)

    # 移除表情图片（有 smilieid 属性的）
    html = re.sub(r'<img[^>]*smilieid="[^"]*"[^>]*/?>',  '', html)

    # 移除 Discuz 图片提示层
    html = re.sub(r'<div[^>]*class="[^"]*aimg_tip[^"]*"[^>]*>.*?</div>', '', html, flags=re.DOTALL)

    # 修正相对链接
    html = re.sub(r'(href|src)="(?!http|javascript|#|mailto|data:)([^"]*)"',
                  lambda m: f'{m.group(1)}="{base_url}/{m.group(2).lstrip("/")}"', html)

    md = _converter.handle(html)

    # 后处理
    # 修复被换行截断的图片/链接语法
    md = re.sub(r'!\[([^\]]*)\]\(([^)]*)\n([^)]*)\)', lambda m: f'![{m.group(1)}]({m.group(2).strip()}{m.group(3).strip()})', md)
    md = re.sub(r'\[([^\]]*)\]\(([^)]*)\n([^)]*)\)', lambda m: f'[{m.group(1)}]({m.group(2).strip()}{m.group(3).strip()})', md)

    # 清理多余空行
    md = re.sub(r'\n{3,}', '\n\n', md)
    md = md.strip()

    return md
