# Production Deployment

## 发布流程

1. 从 `.env.production.example` 创建受权限保护的生产环境文件，并注入 Secret Manager 中的值。
2. `docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet`。
3. 发布前执行 `scripts/backup_postgres.sh /受保护的备份目录` 和 `scripts/backup_artifacts.sh ...`。
4. `docker compose ... build`。
5. `docker compose ... run --rm backend python manage.py migrate --noinput`。
6. `docker compose ... up -d`；Backend 不再在启动命令中隐式执行 Migration。
7. 检查 liveness、readiness、Frontend 代理、Celery Worker ping 与 Beat 日志。
8. 执行登录、关注、提醒、报告、Copilot 的有界 smoke；禁止在输出中打印 Secret。

`docker-compose.production.yml` 隐藏 DB/Redis 端口，增加重启策略和 TLS 反向代理示例。`infra/nginx/production.conf` 中域名和证书路径必须替换。证书由平台/ACME 管理，不放入仓库。

## 临时公网 IP 验收

没有域名证书时，可在获得明确风险授权后叠加 `docker-compose.server.yml`，使用
`infra/nginx/server-http.conf` 仅开放 HTTP 80 端口进行临时验收。该模式会关闭 Secure Cookie 与
HTTPS Redirect，只允许作为过渡方案；不得在不可信网络使用重要密码。正式上线必须绑定域名、
恢复 Secure Cookie / HTTPS Redirect，并切回受信任证书的生产反向代理配置。

## 回滚

应用回滚应先停止写任务，再回滚镜像。Migration 只允许使用经过评审且可逆的迁移；涉及不可逆 Schema 时从备份恢复到隔离实例验证后再决定生产恢复。不得用 `flush`、删除 volume 或重置数据库进行回滚。
