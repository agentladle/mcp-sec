# 更新日志

本项目的所有重要更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
并且本项目遵循 [Semantic Versioning (语义化版本)](https://semver.org/spec/v2.0.0.html)。

> **注意：** 发布前请更新此文件以及 `src/mcp_sec/__init__.py` 中的版本号。

## 环境

| 环境 | 当前版本 | 说明 |
|------|---------|------|
| TestPyPI | `0.1.4` | 测试环境 |
| PyPI | `0.1.4` | 生产环境 |

## 发版流程

1. 更新本文件的目标版本号。
2. 同步更新 `src/mcp_sec/__init__.py` 中的 `__version__`。
3. 构建项目：`python -m build`
4. 上传包：
   - 测试环境：`twine upload --repository testpypi dist/*`
   - 正式环境：`twine upload dist/*`

---

## [0.1.4] - 2026-07-09

### 新增 (Added)
- 新增 `lookup_ticker_cik` 工具，用于解析 ticker ↔ CIK 映射并诊断缺失映射。

### 更改 (Changed)
- 优化下载器在 ticker/CIK 查找失败时的处理逻辑。

## [0.1.3] - 2026-06-17

### 新增 (Added)
- 补充了演示视频。

### 更改 (Changed)
- 优化本地配置路径（迁移至 `~/.agentladle/mcp-sec/`）。

### 修复 (Fixed)
- 修复 Glama Schema 校验问题。

## [0.1.2] - 2026-06-15

### 新增 (Added)
- 正式发布到 PyPI。

### 更改 (Changed)
- 语义重构：`filing_date` 变更为 `report_date`。
- 优化了工具描述。

## [0.1.1]

### 新增 (Added)
- 发布到 TestPyPI 进行测试。

## [0.1.0]

### 新增 (Added)
- 初始版本打包。
