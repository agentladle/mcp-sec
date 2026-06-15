# 📈 AgentLadle MCP - 财务报告数据

*查看其他语言版本：[English](README.md) | [简体中文](README_zh-CN.md)*


**AgentLadle** 是一个专为 AI 开发者和平台设计的专业 Model Context Protocol (MCP) 服务器。

通过接入本服务，您的 AI 助手（如 Claude）将获得强大的数据超能力：能够瞬间检索、提取并深度理解**中国沪深 A 股上市公司（2023 - 2025 年度）的完整财务报告**。

---

## ✨ 核心能力 (Features)

- 🔍 **全文财务检索 (`financialKeywordSearch`)**：在全市场 A 股上市公司的年度报告中，精准定位并搜索特定的关键词与段落。
- 📑 **原版页面提取 (`getFinancialReportPages`)**：直接提取任意公司年报中指定页码的原版无损文本，为大模型提供最精准的上下文。
- 📊 **核心报表定位 (`getFinancialStatementsStartPages`)**：瞬间定位四大合并财务报表（资产负债表、利润表、现金流量表、所有者权益变动表）在财报中的起始页。
- 📖 **智能目录解析 (`getReportChapters`)**：获取任意财务报告完整、结构化的章节目录。
- 🏢 **公司主数据查询 (`searchCompanyInfo`)**：支持通过公司简称或股票代码，快速查询上市公司的基础信息。

---

## 🚀 快速开始

### 1. 获取您的 API Key
AgentLadle 提供的是云端 API 服务。要使用本 MCP 工具，您必须首先获取一个授权 API Key。

> [!IMPORTANT]
> 👉 **[点击这里前往 AgentLadle.com 注册并获取 API Key 免费使用](https://agentladle.com/register)**

### 2. 客户端配置指南

因为 AgentLadle 是云端托管服务，您**完全不需要**在本地安装或运行任何 Java 或 Docker 环境。我们采用了**无状态 HTTP (Stateless HTTP)** 直连方案。

请将以下 JSON 配置段添加到您的 MCP 客户端中（例如 Claude Desktop 或 Cursor）：

```json
{
  "mcpServers": {
    "agentladle-mcp": {
      "type": "streamableHttp",
      "url": "https://mcp.agentladle.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY_HERE"
      }
    }
  }
}
```

*请记得将上述代码中的 `YOUR_API_KEY_HERE` 替换为您在第一步中获取到的真实 API Key。*

---

## 🛠️ 使用场景示例

完成配置后，打开您的 Claude Desktop，直接向 AI 提问即可：
- **财报附注深度解析**：*"分析比亚迪2025年应收账款明细"* 或 *"查找宁德时代2025年资本开支去向"*
- **报表重构与管理分析**：*"提取格力电器2025年资产负债表，并重构为管理用资产负债表"*
- **全市场宏观主题扫描**：*"哪些公司在2025年报提到了‘固态电池’"* 或 *"全市场‘低空经济’相关业务进展"*


