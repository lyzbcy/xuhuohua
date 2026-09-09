# 贡献指南

感谢你愿意参与 `douyin-auto-fire`。

## 提交问题前

1. 先搜索现有 Issue，避免重复提交。
2. 确认已经阅读 README 和对应部署文档。
3. 尽量使用最新版本代码复现问题。
4. 不要在 Issue、日志或截图中提交 Cookie、Storage State、Token、Webhook、账号密码等敏感信息。

## 报告 Bug

请使用仓库提供的 Bug Report 模板，并尽量提供：

- 使用方式：GitHub Actions / Linux / Windows。
- Python、Playwright 与浏览器环境。
- 可复现步骤。
- 预期结果与实际结果。
- 脱敏后的日志、截图或 Trace 信息。
- 最近是否修改过配置、Workflow 或项目代码。

## 提交功能建议

请说明实际使用场景、希望解决的问题，以及你认为合理的实现方式。相比只写“希望增加某功能”，带具体场景的建议更容易被讨论和实现。

## 提交 Pull Request

1. Fork 本仓库并从最新 `main` 创建分支。
2. 一个 PR 尽量只解决一个问题。
3. 保持现有代码结构和风格，避免无关重构。
4. 修改行为逻辑时补充或更新测试。
5. 修改使用方式、配置项或部署流程时同步更新文档。
6. 提交前确认没有把任何真实账号凭证、Cookie、Storage State 或私密配置提交进仓库。
7. 提交代码即表示你同意你的贡献按照本仓库当前许可证一并提供；本项目当前采用 PolyForm Noncommercial License 1.0.0，贡献内容不得改变或绕过项目的非商业使用限制。

推荐分支命名：

- `fix/...`：Bug 修复
- `feat/...`：新功能
- `docs/...`：文档修改
- `chore/...`：维护性修改

## 本地开发

```bash
python -m venv .venv
```

安装依赖：

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
playwright install chromium
```

运行测试：

```bash
pytest
```

在真实发送消息前，请优先使用项目的 Dry Run 能力进行验证。

## PR 描述建议

请在 PR 中说明：

- 修改了什么。
- 为什么需要修改。
- 如何验证。
- 是否会影响现有配置或兼容性。

维护者可能会要求补充复现信息、测试或文档。感谢你的理解和贡献。
