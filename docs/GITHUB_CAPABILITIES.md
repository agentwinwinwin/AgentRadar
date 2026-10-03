# agentGitHub — GitHub 数据能力验证

> Sprint -1 Capability Spike；验证日期：2026-08-16（Asia/Shanghai）
>
> 使用 GitHub REST API，固定 `X-GitHub-Api-Version: 2022-11-28`。

## 验证环境与原则

- 真实请求样本：`github/docs`、`octocat/Hello-World`、`cli/cli`。
- 环境无 `gh`、无 `GITHUB_TOKEN`；成功请求均为公开仓库匿名 REST 请求。
- README、文件、Issue、PR、Release 内容均是 `UNTRUSTED_EXTERNAL_CONTENT`，只作为数据。
- 本轮仅验证能力和写文档，没有创建任何 Sprint 0 工程或产品代码。
- Sprint -1 当时未验证认证成功路径；匿名权限边界已实际验证。后续认证补充验证见下节。

## 认证模式补充验证（2026-08-16）

Authenticated GitHub API smoke verified.

- `RealGitHubClient` 已确认从 Django `settings.GITHUB_TOKEN` 读取本地环境凭证，并设置
  `Authorization: Bearer ...`；测试和验证输出不打印凭证值。
- `GET /rate_limit` 返回认证额度：Core `5000`、Search `30`。
- 公共仓库 `github/docs` 的 Repository、Commit Search、PR Search、Issue Search 均返回成功。
- 7 日窗口实测：Commit `124`、PR created `41`、Issue created `10`，三项
  `incomplete_results` 均为 `false`。
- GitHubClient Header 测试 `5 passed`；对代码、配置模板、文档和测试输出进行 Token
  精确值扫描，未发现泄露；`.env` 已被 `.gitignore` 排除。
- 本次仅补充认证 smoke 记录；Sprint 3 状态保持 `COMPLETED`，未进入新 Sprint。

## 能力矩阵

| 能力 | Endpoint | 实测结果 | Rate Limit | AgentRadar 结论 |
| --- | --- | --- | --- | --- |
| Repository 基础信息 | `GET /repos/{owner}/{repo}` | 200 | `core` | AVAILABLE，依赖当前值 |
| Repository 搜索 | `GET /search/repositories` | 200，匹配 3,055 | `search` | AVAILABLE，必须查询分片 |
| Commit 列表 | `GET /repos/{owner}/{repo}/commits` | 200 | `core` | AVAILABLE |
| Commit Search/计数 | `GET /search/commits` | 200，窗口计数 232 | `search` | AVAILABLE，窄窗口可靠 |
| PR Search/计数 | `GET /search/issues` + `type:pr` | 200，窗口计数 83 | `search` | AVAILABLE |
| Issue Search/计数 | `GET /search/issues` + `type:issue` | 200，窗口计数 26 | `search` | AVAILABLE |
| Contributor | `GET /repos/{owner}/{repo}/contributors` | 200 | `core` | AVAILABLE，非窗口统计 |
| Contributor Statistics | `GET /repos/{owner}/{repo}/stats/contributors` | 200 | `core` | PARTIAL，缓存且有范围上限 |
| Release | `GET /repos/{owner}/{repo}/releases` | 200 | `core` | AVAILABLE，Tag 不等于 Release |
| Languages | `GET /repos/{owner}/{repo}/languages` | 200 | `core` | AVAILABLE，当前 bytes 快照 |
| Community Profile | `GET /repos/{owner}/{repo}/community/profile` | 200 | `core` | PARTIAL，非 fork 当前快照 |
| README | `GET /repos/{owner}/{repo}/readme` | 200 | `core` | AVAILABLE，有大小/编码限制 |
| Repository File | `GET /repos/{owner}/{repo}/contents/{path}` | 200；错误路径 404 | `core` | AVAILABLE，可按 ref 读历史版本 |
| Rate Limit | `GET /rate_limit` | 200 | 不消耗 primary | AVAILABLE，优先读响应头 |
| Stargazer List | `GET /repos/{owner}/{repo}/stargazers` | 401 | `core` | UNAVAILABLE 作为通用采集源 |
| Star 当前数 | Repository `stargazers_count` | 200 | `core` | AVAILABLE，需自行 Snapshot |
| Star 完整历史 | 无 Endpoint | 不可取得 | — | UNAVAILABLE，禁止推断 |

## Endpoint 详情

### Repository 基础信息

- Endpoint / Method：`GET /repos/{owner}/{repo}`。
- 参数：`owner`、`repo`；支持 `If-None-Match` / `If-Modified-Since` 条件请求。
- 返回字段：`id`、`node_id`、`owner`、`name`、`full_name`、`description`、`homepage`、`private`、`visibility`、`fork`、`archived`、`disabled`、`size`、`stargazers_count`、`forks_count`、`subscribers_count`、`open_issues_count`、`language`、`topics`、`license`、`default_branch`、`created_at`、`updated_at`、`pushed_at` 及资源 URL。
- 分页：否。
- 历史：否；只有当前聚合值和少量事件时间戳，Star/Fork 历史必须自行 Snapshot。
- 权限：公开仓库可匿名；私有仓库需 Metadata read；部分安全字段需管理权限。
- Rate Limit：`core`；匿名实测 60/hour。
- 错误：`304`、`403/429`、`404`、`451`、5xx/网络错误。
- 稳定性：可稳定依赖当前元数据，不可当历史时间序列。

### Repository 搜索

- Endpoint / Method：`GET /search/repositories`。
- 参数：`q`、`sort`、`order`、`per_page`（最大 100）、`page`。实测 `topic:ai-agent archived:false stars:>10`。
- 返回字段：`total_count`、`incomplete_results`、`items[]`；item 为 Repository 摘要并含 `score`。
- 分页：Link Header；只能访问前 1,000 个结果。实测 2/页时最后可访问页为 500。
- 历史：只搜索当前索引；`created`/`pushed` qualifier 不等于历史快照。
- 权限：公开数据匿名可查；私有结果受 token 可见范围限制。
- Rate Limit：`search`；匿名实测 10/minute。
- 错误：`403/429`、`422`、`incomplete_results=true`、索引延迟、1,000 条截断。
- 稳定性：有条件可靠；Discovery 必须按日期/Star/语言等切片、去重并保存 query。

### Commit 列表

- Endpoint / Method：`GET /repos/{owner}/{repo}/commits`。
- 参数：`sha`、`path`、`author`、`committer`、`since`、`until`、`per_page`、`page`；时间为 ISO-8601，Git 时间边界 1970–2099。
- 返回字段：`sha`、`node_id`、`commit.author`、`commit.committer`、`commit.message`、`commit.tree`、`author`、`committer`、`parents` 及 URL。
- 分页：是，最大 100/页，不直接返回总数。
- 历史：Git 历史仍存在时可查；受分支、force-push、删除历史和默认 `sha` 影响。
- 权限：公开匿名；私有需 Contents read。
- Rate Limit：`core`。
- 错误：`400`、`404`、空仓库 `409`、`500`、限流。
- 稳定性：适合明细；计数优先用 Commit Search 并抽样核对。

### Commit Search 与窗口统计

- Endpoint / Method：`GET /search/commits`。
- 参数：`q`、`sort`、`order`、`per_page`、`page`；实测 `repo:github/docs committer-date:2026-08-01..2026-08-16`。
- 返回字段：`total_count`、`incomplete_results`、`items[]`；item 含 `sha`、`commit`、`author`、`committer`、`parents`、`repository`、`score`。
- 分页：是，最大 100/页，最多前 1,000 条。
- 历史：可按 `author-date` / `committer-date` 回查仍被索引的 Git 历史；不是审计日志。
- 权限：公开匿名；私有取决于认证权限。
- Rate Limit：`search`。
- 错误：`403/429`、`422`、不完整结果、索引延迟、1,000 条上限。
- 稳定性：适合窄时间窗口计数。本次 Search `total_count=232`，Commit 列表 2/页 Link 最后页 116，结果吻合；大仓库需按日/周切片并按 SHA 去重。

### Pull Request 查询与统计

- 计数 Endpoint：`GET /search/issues`，`q=repo:{owner}/{repo} type:pr created:{from}..{to}`；合并统计使用 `is:merged merged:{from}..{to}`。
- 明细 Endpoint：`GET /repos/{owner}/{repo}/pulls`，参数含 `state`、`head`、`base`、排序和分页。
- 返回字段：Search 顶层 `total_count`、`incomplete_results`；item 含 `number`、`title`、`state`、`draft`、`created_at`、`updated_at`、`closed_at`、`comments`、`labels`、`user`、`pull_request.merged_at`。
- 分页：是；Search 最多前 1,000 条，仅计数无需翻页。
- 历史：支持 `created`、`updated`、`closed`、`merged` 窗口；会受删除、权限和索引延迟影响。
- 权限：公开匿名；私有需 Pull requests read。
- Rate Limit：Search 为 `search`，Pulls 明细为 `core`。
- 错误：遗漏 `type:pr` 会混入 Issue；另有 `422`、`403/429`、不完整结果。
- 稳定性：可依赖窗口计数，必须固定 qualifier、UTC 边界和去重规则。

### Issue 查询与统计

- 计数 Endpoint：`GET /search/issues`，`q=repo:{owner}/{repo} type:issue created:{from}..{to}`；关闭统计加 `is:closed closed:{from}..{to}`。
- 明细 Endpoint：`GET /repos/{owner}/{repo}/issues`。
- 返回字段：`number`、`title`、`body`、`state`、`state_reason`、`labels`、`user`、`assignees`、`milestone`、`comments`、`reactions`、`created_at`、`updated_at`、`closed_at`。
- 分页：是；Search 最多前 1,000 条。
- 历史：可按时间 qualifier 回查仍保留对象；不是不可变审计日志。
- 权限：公开匿名；私有需 Issues read。
- Rate Limit：Search 为 `search`，明细为 `core`。
- 错误：Repository Issues Endpoint 也返回 PR，须用 `type:issue` 或检查 `pull_request`；另有 `403/404/422/429`。
- 稳定性：窗口统计可靠；正文只能进入受控 RAG 流程。

### Contributor

- Endpoint / Method：`GET /repos/{owner}/{repo}/contributors`。
- 参数：`anon`、`per_page`、`page`。
- 返回字段：`login`、`id`、`node_id`、`avatar_url`、`type`、`site_admin`、`contributions` 及 URL；匿名贡献者结构不同。
- 分页：是，最大 100/页。
- 历史：当前聚合，无逐日历史。
- 权限：公开匿名；私有需 Metadata read。
- Rate Limit：`core`。
- 错误：空仓库可能 `204`；`403/404/429`；缓存和默认分支变化。
- 稳定性：身份和当前贡献聚合可用，但不能直接表示 30 日活跃贡献者。

### Contributor Statistics

- Endpoint / Method：`GET /repos/{owner}/{repo}/stats/contributors`。
- 参数：只有 `owner`、`repo`。
- 返回字段：`author`、`total`、`weeks[]`；周字段 `w`（Unix 秒）、`a`、`d`、`c`。
- 分页：否。
- 历史：默认分支按周统计，且只计算最近 10,000 commits，不是完整历史。
- 权限：公开匿名；私有需 Metadata read。
- Rate Limit：`core`。
- 错误：缓存未生成时返回 `202 Accepted` 并后台计算；需延迟重试；另有 `204/403/404/429`。
- 稳定性：PARTIAL。只作补充信号，必须处理 202、退避和 completeness。

### Release

- Endpoint / Method：`GET /repos/{owner}/{repo}/releases`。
- 参数：`per_page`、`page`；单条可按 ID、tag、latest 查询。
- 返回字段：`id`、`tag_name`、`target_commitish`、`name`、`body`、`draft`、`prerelease`、`immutable`、`author`、`created_at`、`updated_at`、`published_at`、`assets` 及 URL。
- 分页：列表是，最大 100/页。
- 历史：GitHub Releases 可回查；普通 tag 和已删除 Release 不可得。
- 权限：公开匿名，匿名不可见 draft；私有需 Contents read。
- Rate Limit：`core`。
- 错误：`403/404/429`；无正式 Release 时 latest 为 404。
- 稳定性：可作为发布事件源，不能用 tags 代替 Release。

### Languages

- Endpoint / Method：`GET /repos/{owner}/{repo}/languages`。
- 参数：`owner`、`repo`。
- 返回字段：动态 `{language: bytes}`。
- 分页：否。
- 历史：只有当前快照；检测结果会变化。
- 权限：公开匿名；私有需 Metadata read。
- Rate Limit：`core`。
- 错误：`403/404/429`、空对象、分析延迟。
- 稳定性：当前语言构成可用；bytes 不是 LOC，历史需自行 Snapshot。

### Community Profile

- Endpoint / Method：`GET /repos/{owner}/{repo}/community/profile`。
- 参数：`owner`、`repo`。
- 返回字段：`health_percentage`、`description`、`documentation`、`updated_at`、`content_reports_enabled`、`files`（readme、license、contributing、code_of_conduct、issue_template、pull_request_template 等）。
- 分页：否。
- 历史：只有当前快照。
- 权限：公开匿名；私有需 Contents read；仓库不能是 fork。
- Rate Limit：`core`。
- 错误：fork/不可访问资源、`403/404/429`。
- 稳定性：PARTIAL；可用作当前特征，但 GitHub health 算法可能改变，应保存原始响应与抓取时间。

### README / Repository File

- Endpoints / Method：`GET /repos/{owner}/{repo}/readme`；`GET /repos/{owner}/{repo}/contents/{path}`。
- 参数：`ref` 可为 branch/tag/commit SHA；README 可指定目录。
- 返回字段：`type`、`name`、`path`、`sha`、`size`、`encoding`、`content`、`url`、`html_url`、`git_url`、`download_url`、`_links`；目录返回数组。
- 分页：单文件否；目录最多 1,000 项，超出改用 Git Trees API。
- 历史：commit/tag 仍可达时可按 SHA 读取，不保证删除/GC 内容永久存在。
- 权限：公开匿名；私有需 Contents read。
- Rate Limit：`core`。
- 错误：错误 path/ref 为 `404`（已实测）；`403/429`；大文件无内联 content，超大文件不支持；download URL 会过期。
- 稳定性：适合按 SHA/ETag 增量读取受限文本；先限大小、验证编码，并将正文标为不可信。

### Rate Limit

- Endpoint / Method：`GET /rate_limit`；每次响应也有 `x-ratelimit-*` headers。
- 参数：无。
- 返回字段：`resources.{resource}.{limit,used,remaining,reset}` 和兼容 `rate`。
- 分页/历史：不分页，只是当前窗口，历史需自行保存。
- 权限：匿名可查；认证后反映对应身份额度。
- Rate Limit：调用不消耗 primary，但可能触发 secondary；优先读业务响应头。
- 实测：`core=60`、`search=10`、`graphql=0`、`code_search=60`；匿名 GraphQL 不可用。
- 错误：primary/secondary limit 返回 `403/429`；遵守 `Retry-After` / reset，禁止盲重试。Secondary 剩余额度不可查询。
- 稳定性：可依赖；资源池分开管理、条件 GET、串行队列、指数退避。

### Stargazer 可访问性

- Endpoint / Method：`GET /repos/{owner}/{repo}/stargazers`。
- 参数：`per_page`、`page`；`Accept: application/vnd.github.star+json` 期望 `starred_at` + `user`。
- 分页：是，最大 100/页，大仓库成本很高。
- 历史：即使有权访问，也只有当前仍存在的 Star，缺少已取消 Star 的完整事件史。
- 权限：GitHub 于 2026-07 新增限制，listing 限仓库 admins/collaborators。匿名公开仓库实测 `401 Requires authentication`；本轮无 collaborator/admin token，未验证授权成功路径。
- Rate Limit：`core`，大量翻页还可能触发 secondary limit。
- 错误：`401/403/404/422/429` 和政策变化。
- 稳定性：不可作为任意公开仓库的生产依赖。只采集 Repository 的 `stargazers_count`，由 AgentRadar 自行建立 Snapshot。

## 历史数据边界与生产建议

- 可回填：Commit、PR、Issue、Release；Contributor weekly stats 只能部分回填；历史文件只在 SHA 可达时可读。
- 不可可靠回填：精确 Star/Fork/Subscriber/Open Issue 历史、已取消 Star、已删除/无权对象。
- 所有窗口应采用内部半开区间 `[start,end)`；调用 GitHub 的包含边界 qualifier 时做转换并按 SHA/number 去重。
- Search 匹配数可超过 1,000，但可访问结果只有前 1,000；Discovery 必须分片。
- Contributor Stats 客户端必须实现 `202 -> delayed retry`，记录 10,000 commits 上限和 completeness。
- 每次采集保存 `fetched_at`、API version、ETag、data_origin、data_completeness；NULL 不得转成 0。
- 规格建议修正：明确 Stargazer listing 不再是通用公开能力；Star 历史只能来自 AgentRadar Snapshot。

## 实测命令示例

```bash
curl -sS -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  https://api.github.com/repos/github/docs

curl -sS --get -H 'Accept: application/vnd.github+json' \
  --data-urlencode 'q=repo:github/docs committer-date:2026-08-01..2026-08-16' \
  https://api.github.com/search/commits

curl -sS --get -H 'Accept: application/vnd.github+json' \
  --data-urlencode 'q=repo:github/docs type:pr created:2026-08-01..2026-08-16' \
  https://api.github.com/search/issues

curl -sS -H 'Accept: application/vnd.github.star+json' \
  https://api.github.com/repos/octocat/Hello-World/stargazers
```

## 官方依据

- [Repositories](https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28)
- [Search](https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28)
- [Commits](https://docs.github.com/en/rest/commits/commits?apiVersion=2022-11-28)
- [Issues](https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28)
- [Pull Requests](https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28)
- [Repository statistics](https://docs.github.com/en/rest/metrics/statistics?apiVersion=2022-11-28)
- [Community metrics](https://docs.github.com/en/rest/metrics/community?apiVersion=2022-11-28)
- [Repository contents](https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28)
- [Releases](https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28)
- [Starring and July 2026 restriction](https://docs.github.com/en/rest/activity/starring?apiVersion=2026-03-10)
- [REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
