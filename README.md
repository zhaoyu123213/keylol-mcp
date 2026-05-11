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

采集 Keylol 论坛帖子数据，支持三种模式：

- **按板块+日期**：爬取指定板块在指定日期的所有帖子
- **按帖子ID**：只爬取单个帖子
- **最新发表**：爬取全站最新发表页面（`forum.php?mod=guide&view=newthread`）

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `date` | string | 今天 | 采集日期，格式 YYYY-MM-DD |
| `tid` | string | - | 指定帖子 ID（提供时忽略 date 和 mode） |
| `fid` | int | 271 | 板块 ID（271=慈善包板块） |
| `mode` | string | - | 采集模式：`"newthread"` 爬取全站最新发表，留空按板块采集 |
| `max_pages` | int | 3 | 列表翻页上限 |
| `max_comments` | int | 50 | 每帖最多评论数 |
| `include_comments` | bool | true | 是否采集评论 |
| `format` | string | "markdown" | 输出格式："json" 或 "markdown" |
| `output_dir` | string | "./keylol_output" | 文件保存根目录 |
| `request_delay` | float | 0.6 | 请求间隔（秒） |

### 输出目录结构

文件按来源自动分子目录：

```
keylol_output/
├── newthread/          # mode="newthread" 最新发表
│   └── 2026-05-11/
│       ├── 2026-05-11_1037474.md
│       └── ...
├── f271/               # 按板块采集（fid=271）
│   └── 2026-05-11/
│       └── ...
├── f319/               # 按板块采集（fid=319）
│   └── 2026-05-11/
│       └── ...
└── tid/                # 按帖子ID采集
    └── 2026-05-11_1034537.md
```

### 返回值

```json
{
  "success": true,
  "threads_scraped": 19,
  "files_written": ["keylol_output/newthread/2026-05-11/2026-05-11_1037474.md"],
  "errors": []
}
```

### 使用示例

爬取全站今日最新帖子（日报模式）：
```
scrape_keylol(mode="newthread")
```

爬取昨天的最新帖子：
```
scrape_keylol(mode="newthread", date="2026-05-10")
```

采集慈善包板块今天的帖子：
```
scrape_keylol(fid=271)
```

采集指定帖子：
```
scrape_keylol(tid="1034537")
```

采集其他板块、输出 JSON：
```
scrape_keylol(fid=161, format="json", date="2026-04-01")
```

## 板块 fid

| fid | 板块 |
|-----|------|
| 271 | 慈善包 |
| 319 | 福利放送 |
| 234 | 购物心得 |
| 161 | 热点聚焦 |
| 257 | 华语汉化 |
| 148 | 谈天说地 |
| 251 | 综合讨论 |

其他板块的 fid 可以在 Keylol 对应板块页面的 URL 中找到。

## Steering 文件（AI 工作流参考）

`steering/` 目录下提供了配合本 MCP 使用的 AI steering 文件示例，可用于 Kiro 或其他支持 steering/skill 的 AI IDE：

- `keylol-daily-digest.md` — 日报生成规则：爬取当日帖子后按板块分类汇总

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
