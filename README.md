# keylol-mcp

Keylol 论坛 MCP Server — 通过 MCP 协议采集[其乐论坛](https://keylol.com)帖子数据，供 AI 客户端调用。

## 安装

```bash
uvx --from git+https://github.com/zhaoyu123213/keylol-mcp keylol-mcp
```

## 配置

在 `mcp.json` 中添加：

```json
{
  "mcpServers": {
    "keylol-scraper": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/zhaoyu123213/keylol-mcp", "keylol-mcp"],
      "env": {
        "KEYLOL_COOKIE": "你的 Keylol 登录 Cookie"
      }
    }
  }
}
```

### 获取 Cookie

1. 登录 [keylol.com](https://keylol.com)
2. 打开浏览器开发者工具 → Network → 任意请求 → 复制 Cookie 请求头的值
3. 填入 `KEYLOL_COOKIE` 环境变量

## 工具：`scrape_keylol`

采集 Keylol 论坛帖子数据，支持按日期批量采集或按帖子 ID 单独采集。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `date` | string | 今天 | 采集日期，格式 YYYY-MM-DD |
| `tid` | string | - | 指定帖子 ID（提供时忽略 date） |
| `fid` | int | 319 | 板块 ID（319=慈善包板块） |
| `max_pages` | int | 3 | 列表翻页上限 |
| `max_comments` | int | 50 | 每帖最多评论数 |
| `include_comments` | bool | true | 是否采集评论 |
| `format` | string | "markdown" | 输出格式："json" 或 "markdown" |
| `output_dir` | string | "./keylol_output" | 文件保存目录 |
| `request_delay` | float | 0.6 | 请求间隔（秒） |

### 返回值

```json
{
  "success": true,
  "threads_scraped": 3,
  "files_written": ["./keylol_output/2026-04-09_1034537.md"],
  "errors": []
}
```

### 使用示例

采集今天慈善包板块的帖子：
```
scrape_keylol()
```

采集指定帖子：
```
scrape_keylol(tid="1034537")
```

采集其他板块、输出 JSON：
```
scrape_keylol(fid=161, format="json", date="2026-04-01")
```

## 常用板块 fid

| 板块 | fid |
|------|-----|
| 慈善包 | 319 |
| Steam 综合讨论 | 161 |
| 优惠信息 | 150 |

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
