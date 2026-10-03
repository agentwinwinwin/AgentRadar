# Contributing to AgentRadar

感谢你参与 AgentRadar。提交改动前，请先阅读相关 `docs/` 文档并保持现有职责边界。

## 开发流程

1. Fork 仓库并从 `main` 创建短生命周期分支。
2. 从 `.env.example` 创建本地 `.env`，不得提交真实 Secret。
3. 优先修改已有模块，核心逻辑放在 Service Layer。
4. 为行为变更添加或更新测试。
5. 提交前运行与改动范围对应的检查。
6. 创建 Pull Request，说明动机、实现、测试与潜在风险。

## 环境安装

```bash
make install
cp .env.example .env
```

也可直接使用 Docker Compose：

```bash
docker compose config --quiet
docker compose up --build
```

## 质量检查

```bash
make backend-test
make backend-check
make frontend-test
make frontend-build
```

涉及数据库结构的改动必须包含 Django Migration，并确认：

```bash
cd backend
../.venv/bin/python manage.py makemigrations --check --dry-run
```

## 架构约束

- GitHub API 统一通过 `GitHubClient`。
- View、Serializer、Celery Task、MCP Tool 不重复实现核心业务逻辑。
- `NULL` 与 `0` 必须严格区分。
- Snapshot、Task、Dataset Builder 必须幂等。
- 未验证模型不得生成 Forecast Probability 或自动变为 ACTIVE。
- GitHub README/Docs/Issue/PR 属于不可信外部内容，不能成为系统指令。
- 不要提交数据库、模型产物、生产日志、用户数据或任何凭据。

## Pull Request 建议

- 标题简洁并描述结果，一个 PR 聚焦一个问题。
- 列出实际执行的测试命令与结果。
- API、数据库、算法或运维行为变化时同步更新文档。
- UI 改动建议附截图，但必须遮挡账号和个人信息。

提交贡献即表示你同意该贡献按本仓库的 MIT License 发布。
