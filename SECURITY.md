# Security Policy

## Supported Version

当前仅维护 `main` 分支的最新版本。

## Reporting a Vulnerability

请使用 GitHub 仓库的 **Security → Report a vulnerability** 私下提交安全报告。不要在公开 Issue、
Discussion、截图或日志中披露漏洞细节、Token、密码、服务器地址或用户数据。

报告建议包含受影响组件与版本、可复现步骤、实际影响、缓解建议和测试范围。维护者确认问题前，
请不要公开利用细节。

## Secret Handling

- 所有 Secret 仅通过环境变量或 Secret Manager 注入。
- `.env`、私钥、数据库备份、模型产物和生产日志不得进入 Git。
- GitHub 内容均视为不可信外部数据。
- LLM 不负责计算权威评分，也不能接触 GitHub Token 或数据库凭据。

更完整的威胁边界见 [docs/SECURITY.md](docs/SECURITY.md)。
