# Backup and Restore

## 范围与策略

- PostgreSQL：每日 custom-format `pg_dump`，至少保留7个日备份和4个周备份；备份需加密、异地保存。
- Model Artifact：每次模型 Registry/Artifact 变化后备份 `/ml/artifacts`，以 Registry SHA-256 校验。
- Redis：不是业务事实主库；Session、Lock、Celery Result 可丢失，恢复后重新登录/重放幂等任务。
- `.env`、Token 和密钥由 Secret Manager 备份，不打进 DB dump 或 artifact archive。

## PostgreSQL 恢复演练

1. 使用 `scripts/backup_postgres.sh` 生成 dump，并保存生成前关键表 count。
2. 创建与生产隔离的临时 PostgreSQL 数据库，禁止覆盖当前数据库。
3. `createdb` 后以 `pg_restore --clean --if-exists --no-owner --dbname TEST_DB DUMP` 恢复。
4. 对 Repository、Snapshot、Activity、Trend、Potential、Model、Knowledge、Watchlist 等关键表核对 count。
5. 在隔离库运行 `manage.py check`、readiness 和只读 smoke。
6. 记录 dump 大小、开始/结束时间、count 差异与 SHA-256；验证后删除隔离测试数据库。

生产恢复必须由人工批准并在维护窗口执行。不得把恢复演练指向 `DATABASE_URL` 当前库。Model Artifact 恢复后逐项计算 SHA-256 与 Registry 对比；不一致的模型不得 ACTIVE。
