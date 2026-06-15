# 版本追踪

> 发布前修改版本号只需更新此文件和 `src/mcp_sec/__init__.py`。

| 环境 | 当前版本 | 说明 |
|------|---------|------|
| TestPyPI | `0.1.2` | 测试环境（同版本不可重复上传,需递增） |
| PyPI | `0.1.2` | 生产环境（已发布版本不可覆盖，必须递增） |

## 发版流程

1. 更新本文件的目标版本号
2. 同步更新 `src/mcp_sec/__init__.py` 中的 `__version__`
3. 构建：`python -m build`
4. 上传：`twine upload --repository testpypi dist/*`（测试）或 `twine upload dist/*`（正式）

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| 0.1.0 | — | 首次发布到 PyPI |
| 0.1.1 | — | 已发布到 TestPyPI |
| 0.1.2 | 2026-06-15 | 已发布到 PyPI；filing_date→report_date 语义重构；工具描述优化 |
