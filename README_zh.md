# AgentLadle MCP SEC

[English](README.md) | **中文** | 📺 [观看演示视频](https://www.youtube.com/watch?v=qZteRG7WvIQ)

> 🇨🇳 **中国 A 股市场** — 沪深上市公司云端 MCP 服务。[查看文档](Chinese-A-share-MCP-README_zh-CN.md) | [获取 API Key](https://agentladle.com/register)

一个基于 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 的服务器，提供**发现、下载、解析和搜索**美国 SEC 财务报告的工具。

它使 AI 助手（Claude、Cursor 等）能够通过 6 个结构化工具访问 SEC EDGAR 数据 —— 从发现可用的报告文件到在页面内进行关键词搜索。

## 功能特性

- **6 个 MCP 工具**提供基于状态驱动的 SEC 数据检索（直接搜索，按需触发下载/解析的回退机制）
- **专业的 SEC 文档解析**，基于 [edgartools](https://github.com/dgunning/edgar-tools) —— 精准的 iXBRL 报告分页检测和结构化节点树提取
- **本地关键词搜索**，采用 TF + 位置加权评分，零外部依赖
- **幂等操作** —— 已下载/已解析的文件会自动跳过
- **零配置安装** —— 只需一行添加到 MCP 客户端，无需克隆或手动设置
- **纯 Python**，跨平台（Windows / macOS / Linux）

## 前置要求

- **Python 3.10+** — [下载 Python](https://www.python.org/downloads/)
- **uv** — [安装 uv](https://docs.astral.sh/uv/getting-started/installation/)

> **提示：** 安装 uv 后，请重启终端和 MCP 客户端（如 Cherry Studio），确保 `uv` 命令可被识别。

## 快速开始

添加到你的 MCP 客户端配置中（Claude Desktop、Cursor 等）：

```json
{
  "mcpServers": {
    "mcp-sec": {
      "command": "uvx",
      "args": ["agentladle-mcp-sec"],
      "env": {
        "SEC_EMAIL": "your@email.com"
      }
    }
  }
}
```

就这么简单。`uvx` 会自动从 PyPI 下载包及其依赖 —— 无需克隆、无需手动安装、无需配置路径。

> ⚠️ **SEC 邮箱要求：** 请将 `your@email.com` 替换为你的真实邮箱。SEC 要求 User-Agent 头部中包含有效邮箱，使用虚假邮箱可能导致 IP 被封禁。

### 替代方案：pip 安装

如果你更喜欢自己管理环境：

```bash
pip install agentladle-mcp-sec
```

然后配置：

```json
{
  "mcpServers": {
    "mcp-sec": {
      "command": "agentladle-mcp-sec",
      "env": {
        "SEC_EMAIL": "your@email.com"
      }
    }
  }
}
```

### 替代方案：从源码运行（本地开发）

克隆仓库并直接运行：

```bash
git clone https://github.com/agentladle/mcp-sec.git
```

然后配置你的 MCP 客户端：

```json
{
  "mcpServers": {
    "mcp-sec": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-sec", "agentladle-mcp-sec"],
      "env": {
        "SEC_EMAIL": "your@email.com"
      }
    }
  }
}
```

将 `/path/to/mcp-sec` 替换为克隆仓库的实际路径。

## 数据流

```
SEC EDGAR API                     本地文件 (~/.agentladle/mcp-sec/data/)
──────────────                    ──────────────────────────────
company_tickers.json   ──→       company_tickers.json         (股票代码→CIK 映射)
                                     │
SEC Submissions API    ──→        html/*.htm                  (工具 2：下载)
                                     │
edgartools 解析        ──→        json/*.json                 (工具 3：解析，分页)
                                     │
本地 TF 搜索           ──→        搜索结果                     (工具 4：关键词搜索)
页面范围读取           ──→        页面内容                     (工具 5：读取页面)
目录查询               ──→        目录                         (工具 6：获取目录)
```

## 工具列表

| # | 工具 | 描述 |
|---|------|------|
| 1 | `list_sec_filings` | 发现公司可用的 SEC 报告文件 |
| 2 | `download_sec_report` | 下载指定的 SEC 报告（HTML 格式） |
| 3 | `parse_sec_report` | 使用 edgartools 将 HTML 解析为分页 JSON |
| 4 | `keyword_search` | 全文关键词搜索，带 TF 相关性评分 |
| 5 | `get_report_pages` | 按页码范围读取报告内容 |
| 6 | `get_report_toc` | 获取目录页 |

### 工具 1：`list_sec_filings`

列出公司可用的 SEC 报告文件。仅当用户未提供任何年份/日期信息，或尝试下载因日期错误失败时，才使用此工具查询可用列表。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `ticker` | string | ✅ | 股票代码，例如 `"AAPL"` |
| `form` | string | ❌ | 报告类型过滤，例如 `"10-K"`。省略则列出所有财务报告类型（10-K、10-Q、20-F、6-K、8-K、40-F） |
| `limit` | int | ❌ | 最大返回数量，默认 5，最大 20 |

### 工具 2：`download_sec_report`

从 EDGAR 下载指定的 SEC 报告。每次调用下载一份报告。幂等操作（文件已存在且有效时会跳过）。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `ticker` | string | ✅ | 股票代码，例如 `"AAPL"` |
| `form` | string | ✅ | 报告类型：`"10-K"`、`"10-Q"`、`"20-F"`、`"6-K"` |
| `report_date` | string | ✅ | 报告日期（财政年度截止日期），例如 `"2025-01-31"` |

### 工具 3：`parse_sec_report`

将已下载的 HTML 报告解析为分页 JSON。使用 edgartools 的 `mark_page_breaks()` + `parse_html()` 进行专业的 SEC 文档解析。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `ticker` | string | ✅ | 股票代码 |
| `form` | string | ✅ | 报告类型 |
| `report_date` | string | ✅ | 报告日期（财政年度截止日期） |

### 工具 4：`keyword_search`

跨所有页面的全文关键词搜索。结果按 TF + 位置加权评分排序。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `ticker` | string | ✅ | 股票代码 |
| `form` | string | ✅ | 报告类型 |
| `report_date` | string | ✅ | 报告日期（财政年度截止日期） |
| `keywords` | string[] | ✅ | 1–5 个搜索关键词 |
| `match_mode` | string | ❌ | `"ANY"`（默认，任一键词匹配即可）/ `"ALL"`（所有关键词都须匹配） |
| `max_results` | int | ❌ | 最大返回结果数，默认 5，最大 50 |

### 工具 5：`get_report_pages`

按页码范围读取完整的页面内容。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `ticker` | string | ✅ | 股票代码 |
| `form` | string | ✅ | 报告类型 |
| `report_date` | string | ✅ | 报告日期（财政年度截止日期） |
| `start_page` | int | ✅ | 起始页码（从 1 开始） |
| `page_count` | int | ❌ | 返回页数，默认 3，最大 5 |

### 工具 6：`get_report_toc`

获取目录页。在前 10 页中搜索 "Table of Contents"。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `ticker` | string | ✅ | 股票代码 |
| `form` | string | ✅ | 报告类型 |
| `report_date` | string | ✅ | 报告日期（财政年度截止日期） |

## 配置

首次运行时，会在 `~/.agentladle/mcp-sec/config.yaml` 创建默认配置文件：

```yaml
sec:
  email: ""

paths:
  data_dir: "~/.agentladle/mcp-sec/data"
  html_dir: "~/.agentladle/mcp-sec/data/html"
  json_dir: "~/.agentladle/mcp-sec/data/json"

download:
  delay_between_requests: 0.2
  min_file_size: 5000
```

`email` 字段用于构建符合 SEC 规范的 User-Agent 头部（`AgentLadleMcpSec {email}`）。你可以通过以下三种方式配置（优先级从高到低）：

1. **环境变量** `SEC_EMAIL` —— 推荐，在 MCP 客户端 JSON 配置中设置
2. **配置文件** —— 编辑 `~/.agentladle/mcp-sec/config.yaml`，设置 `email`
3. **默认值** —— 若为空，则使用占位邮箱（不推荐在生产环境使用）

> ⚠️ **SEC User-Agent 政策**：SEC 要求 User-Agent 头部中包含真实邮箱。使用默认占位邮箱可能导致 IP 被封禁。

## 数据目录结构

```
~/.agentladle/mcp-sec/
├── config.yaml                        # 配置文件（自动创建）
└── data/
    ├── company_tickers.json           # 股票代码→CIK 映射（自动下载并缓存）
    ├── html/                          # 下载的 HTML 报告文件
    │   ├── AAPL_10-K_2025-01-31.htm
    │   └── ...
    └── json/                          # 解析后的分页 JSON 文件
        ├── AAPL_10-K_2025-01-31.json
        └── ...
```

**文件命名规则：** `{股票代码}_{报告类型}_{报告日期}.htm/json`

## 使用示例

工具集采用了 **EAFP（基于错误回退）** 的设计理念。AI 助手应优先尝试直接检索数据，仅在收到“文件未找到”报错时才去执行下载操作。

**场景 A：文件已存在本地（最短路径）**
```
用户："帮我分析下 AAPL 最新 10-K 的管理层意见"

1. keyword_search(ticker="AAPL", form="10-K", report_date="2025-01-31", keywords=["management", "discussion"])
   → 瞬间返回匹配关键词的页面摘要。
```

**场景 B：本地无文件（触发回退机制）**
```
用户："特斯拉 2024 年的营收是多少？"

1. keyword_search(ticker="TSLA", form="10-K", report_date="2024-12-31", keywords=["revenue", "net sales"])
   → 报错：文件未找到。
   
2. download_sec_report(ticker="TSLA", form="10-K", report_date="2024-12-31")
   → 下载 HTML 报告。
   
3. parse_sec_report(ticker="TSLA", form="10-K", report_date="2024-12-31")
   → 解析报告内容。
   
4. keyword_search(ticker="TSLA", form="10-K", report_date="2024-12-31", keywords=["revenue", "net sales"])
   → 重试搜索并返回结果。
```

## 技术栈

| 组件 | 选型 | 用途 |
|------|------|------|
| MCP 框架 | `mcp` (FastMCP) | MCP 服务器，stdio 传输 |
| HTTP 客户端 | `httpx` | SEC API 请求和文件下载 |
| HTML 解析 | `edgartools` + `beautifulsoup4` | 专业的 SEC iXBRL 解析（分页检测 + 节点树） |
| 搜索 | Python 内置 | TF + 位置加权评分 |
| 配置 | `pyyaml` | YAML 配置文件 |

## 项目结构

```
src/mcp_sec/
├── __init__.py
├── server.py          # MCP 服务器入口
├── config.py          # 配置加载（~/.agentladle/mcp-sec/config.yaml，单例缓存）
├── models.py          # 数据模型
├── tools/
│   ├── list_filings.py # 工具 1：list_sec_filings
│   ├── download.py    # 工具 2：download_sec_report
│   ├── parse.py       # 工具 3：parse_sec_report
│   ├── search.py      # 工具 4：keyword_search
│   ├── page.py        # 工具 5：get_report_pages
│   └── toc.py         # 工具 6：get_report_toc
└── services/
    ├── downloader.py  # SEC EDGAR 下载 + 股票代码→CIK 转换
    ├── parser.py      # HTML→JSON 解析（edgartools）
    └── searcher.py    # 本地 JSON 搜索 + TF 评分
```

## 许可证

MIT
