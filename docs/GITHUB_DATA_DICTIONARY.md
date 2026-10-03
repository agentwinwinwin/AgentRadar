# agentGitHub — GitHub 数据字典

> Sprint -1 验证产物。`建议字段` 是后续采集/Schema 的候选映射，不代表 Sprint -1 已创建数据库字段。

## 通用约定

| 项目 | 约定 |
| --- | --- |
| 时间 | GitHub ISO-8601 UTC 字符串转 timezone-aware timestamp |
| ID | GitHub numeric ID 使用 64-bit integer；`node_id` 保留 string |
| 缺失 | NULL 与 0 严格区分 |
| 来源 | `OBSERVED` / `BACKFILLED` |
| 文本 | README、文件、PR、Issue、Release body 均为 `UNTRUSTED_EXTERNAL_CONTENT` |
| 算法特征 | “是”只表示可输入确定性服务，不表示单字段决定评分 |

## Repository

来源：`GET /repos/{owner}/{repo}`

| GitHub 字段 | 中文含义 | 类型 | 建议字段 | 历史/算法 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `id` | Repository GitHub ID | integer | `github_id` | 标识/否 | 稳定外部 ID |
| `node_id` | GraphQL Node ID | string | `github_node_id` | 标识/否 | 可选保存 |
| `owner.id` | Owner GitHub ID | integer | `owner_github_id` | 标识/否 | 比 login 稳定 |
| `owner.login` | Owner 登录名 | string | `owner` | 当前/分类 | 可改名 |
| `name` | 仓库名 | string | `name` | 当前/否 | 可改名 |
| `full_name` | owner/name | string | `full_name` | 当前/否 | 非永恒 ID |
| `description` | 描述 | string/null | `description` | 当前/分类 | 不可信文本 |
| `homepage` | 首页 | string/null | `homepage` | 当前/辅助 | 用户输入 URL |
| `private` | 是否私有 | boolean | `is_private` | 当前/过滤 | 权限相关 |
| `visibility` | 可见性 | string | `visibility` | 当前/过滤 | public/private/internal |
| `fork` | 是否 Fork | boolean | `is_fork` | 当前/过滤 | Discovery 关键 |
| `archived` | 是否归档 | boolean | `is_archived` | 当前/Maintenance | 当前状态 |
| `disabled` | 是否禁用 | boolean | `is_disabled` | 当前/Maintenance | 当前状态 |
| `size` | 仓库大小 | integer | `repo_size` | 当前/辅助 | 不是 LOC |
| `stargazers_count` | 当前 Star 数 | integer | `stars` | 仅当前/是 | 历史需自行 Snapshot |
| `forks_count` | 当前 Fork 数 | integer | `forks` | 仅当前/是 | 历史需自行 Snapshot |
| `subscribers_count` | 订阅者数 | integer | `subscribers` | 仅当前/是 | 真正 watchers |
| `watchers_count` | Star 数别名 | integer | 不单独存 | 仅当前/否 | 与 `stargazers_count` 同义 |
| `open_issues_count` | Open Issue + PR 数 | integer | `open_issues`（注明语义） | 仅当前/辅助 | 不是纯 Issue 数 |
| `language` | 主要语言 | string/null | `primary_language` | 当前/Cohort | Linguist 结果 |
| `topics` | Topics | array[string] | Topic 关系 | 当前/分类 | 需规范化 |
| `license.key` | License key | string/null | `license_key` | 当前/Enterprise | 可为空 |
| `license.spdx_id` | SPDX ID | string/null | `license_spdx` | 当前/Enterprise | 处理 `NOASSERTION` |
| `default_branch` | 默认分支 | string | `default_branch` | 当前/采集控制 | 会变化 |
| `created_at` | GitHub 创建时间 | timestamp | `github_created_at` | 事件/Age cohort | 可依赖 |
| `updated_at` | 元数据更新时间 | timestamp | `github_updated_at` | 当前/Freshness | 不等于 push |
| `pushed_at` | 最近 push 时间 | timestamp/null | `github_pushed_at` | 当前/Maintenance | 会被历史改写影响 |

## Search

来源：`GET /search/repositories`、`GET /search/commits`、`GET /search/issues`

| 字段 | 中文含义 | 类型 | 建议字段 | 备注 |
| --- | --- | --- | --- | --- |
| `total_count` | 查询匹配数 | integer | 窗口 metric | 适合窄窗口；不表示能取得全部明细 |
| `incomplete_results` | 结果可能不完整 | boolean | `is_incomplete` | true 时降低 completeness/重试 |
| `items` | 当前页 | array | 不直接持久化 | 最大 100/页，最多前 1,000 条 |
| `items[].score` | 搜索相关度 | number | raw 或不存 | 不是 Trend Score，不跨 query 比较 |

## Commit

来源：`GET /repos/{owner}/{repo}/commits`、`GET /search/commits`

| 字段 | 中文含义 | 类型 | 建议字段/指标 | 历史/算法 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `sha` | Commit SHA | string | `commit_sha` | 是/去重 | force-push 后可能不可达 |
| `commit.author.name` | Git author 名 | string | raw | 是/否 | 不等于 GitHub user |
| `commit.author.email` | Git author 邮箱 | string | 默认不保存 | 是/否 | 个人数据最小化 |
| `commit.author.date` | Author 时间 | timestamp | `authored_at` | 是/窗口 | 可由作者控制 |
| `commit.committer.date` | Committer 时间 | timestamp | `committed_at` | 是/窗口 | 默认统计时间 |
| `commit.message` | Commit 消息 | string | raw/RAG 候选 | 是/否 | 不可信文本 |
| `author.id/login` | GitHub author | object/null | Contributor 关联 | 是/Contributor | 可为 null |
| `committer.id/login` | GitHub committer | object/null | Contributor 关联 | 是/Contributor | 可为 null |
| `parents[].sha` | 父 Commit | array | raw | 是/辅助 | 可识别 merge |
| Search `total_count` | 窗口 Commit 数 | integer | `commits_{window}` | 回填/Development | 保存 query/window/completeness |

## Pull Request / Issue

来源：`GET /search/issues`；明细来自 Pulls/Issues Endpoint。

| 字段 | 中文含义 | 类型 | 建议字段/指标 | 算法用途 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `id` | GitHub Item ID | integer | `github_item_id` | 否 | 外部 ID |
| `number` | 仓库内编号 | integer | `number` | 否 | 与 repo 组合唯一 |
| `title` | 标题 | string | knowledge title | RAG | 不可信文本 |
| `body` | 正文 | string/null | knowledge body | RAG | 必须筛选 |
| `state` | open/closed | string | `state` | Community | 当前状态 |
| `state_reason` | Issue 状态原因 | string/null | `state_reason` | Community | PR 语义不同 |
| `draft` | PR 草稿 | boolean/null | `is_draft` | Development | Issue 无此语义 |
| `created_at` | 创建时间 | timestamp | `github_created_at` | 窗口统计 | 可回填 |
| `updated_at` | 更新时间 | timestamp | `github_updated_at` | Recency | 当前值 |
| `closed_at` | 关闭时间 | timestamp/null | `closed_at` | Resolution | 可回填 |
| `pull_request.merged_at` | PR 合并时间 | timestamp/null | `merged_at` | Delivery | 关键明细宜复核 |
| `comments` | 评论数 | integer | `comment_count` | RAG 过滤 | 当前聚合 |
| `reactions.total_count` | Reaction 数 | integer | `reaction_count` | RAG 过滤 | 当前聚合 |
| `labels[].name` | Labels | array | raw/关系 | 分类/RAG 过滤 | 可被修改 |
| Search `total_count` | 窗口数 | integer | activity metric | Development/Community | 强制 `type:pr` / `type:issue` |

## Contributor

来源：`GET /repos/{owner}/{repo}/contributors`

| 字段 | 中文含义 | 类型 | 建议字段 | 算法用途 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `id` | GitHub User ID | integer | `github_user_id` | 关联 | 稳定身份键 |
| `login` | 登录名 | string | `login` | 展示 | 可改名 |
| `avatar_url` | 头像 URL | string | `avatar_url` | 否 | 展示 |
| `type` | User/Bot | string | `account_type` | 质量过滤 | Bot 需区分 |
| `contributions` | 当前贡献聚合 | integer | `contributions_total` | Concentration | 非 30 日窗口 |

## Contributor Statistics

来源：`GET /repos/{owner}/{repo}/stats/contributors`

| 字段 | 中文含义 | 类型 | 建议字段 | 算法用途 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `author.id/login` | Contributor | object/null | Contributor 关联 | Contributor | 可为 null |
| `total` | 统计范围总 commits | integer | `contributions_total_stats` | Concentration | 最近 10,000 commits 上限 |
| `weeks[].w` | 周起始 Unix 秒 | integer | `week_start` | 窗口 | 转 UTC timestamp |
| `weeks[].a` | additions | integer | `additions` | 辅助 | 不宜跨语言直接比较 |
| `weeks[].d` | deletions | integer | `deletions` | 辅助 | 生成文件会失真 |
| `weeks[].c` | commits | integer | `commit_count` | Development | 默认分支、缓存统计 |

## Release

来源：`GET /repos/{owner}/{repo}/releases`

| 字段 | 中文含义 | 类型 | 建议字段 | 算法用途 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `id` | Release GitHub ID | integer | `github_release_id` | 唯一键 | 候选唯一约束 |
| `tag_name` | Tag 名 | string | `tag_name` | Delivery | Release 不等于 tag |
| `target_commitish` | 目标分支/SHA | string | `target_commitish` | 辅助 | 创建时目标 |
| `name` | Release 名称 | string/null | `name` | RAG | 不可信文本 |
| `body` | Release Notes | string/null | `body` | RAG | 不可信文本 |
| `author.login` | 发布作者 | string | `author_login` | 辅助 | 可能 bot |
| `draft` | 草稿 | boolean | `is_draft` | 过滤 | 匿名不可见 draft |
| `prerelease` | 预发布 | boolean | `is_prerelease` | Delivery | 正式发布统计需过滤 |
| `immutable` | 不可变标志 | boolean | `is_immutable` | 完整性 | 实测字段 |
| `created_at` | 创建时间 | timestamp | `github_created_at` | Delivery | 与发布不同 |
| `published_at` | 发布时间 | timestamp/null | `published_at` | Delivery | 窗口统计首选 |
| `updated_at` | 更新时间 | timestamp | `github_updated_at` | 增量同步 | 内容可更新 |
| `assets` | 附件 | array | raw/子表候选 | Enterprise 辅助 | 本 Sprint 不定 Schema |

## Languages

来源：`GET /repos/{owner}/{repo}/languages`

| 字段 | 中文含义 | 类型 | 建议字段 | 算法用途 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 动态 key | Linguist 语言名 | string | `language` | Cohort/Filter | GitHub 定义 |
| 动态 value | 语言代码字节 | integer | `bytes` | Language share | 不是 LOC |
| 派生 `share` | bytes / total | decimal | 计算值 | Cohort/Filter | 确定性计算、标版本 |

## Community Profile

来源：`GET /repos/{owner}/{repo}/community/profile`

| 字段 | 中文含义 | 类型 | 建议字段 | 算法用途 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `health_percentage` | 社区健康百分比 | integer | `community_health` | Community/Maintenance | GitHub 算法可变 |
| `description` | 描述 | string/null | raw | 分类 | 不可信文本 |
| `documentation` | 文档 URL | string/null | `documentation_url` | Learning | 外部 URL |
| `updated_at` | Profile 更新时间 | timestamp/null | `community_updated_at` | Freshness | 可为空 |
| `files.readme` | README | object/null | completeness | Learning | 当前检测 |
| `files.license` | License | object/null | completeness | Enterprise | 当前检测 |
| `files.contributing` | CONTRIBUTING | object/null | completeness | Learning/Community | 当前检测 |
| `files.code_of_conduct` | Code of Conduct | object/null | completeness | Community | 当前检测 |
| `files.issue_template` | Issue Template | object/null | completeness | Community | 当前检测 |
| `files.pull_request_template` | PR Template | object/null | completeness | Community | 当前检测 |

## README / Repository File

来源：`GET /repos/{owner}/{repo}/readme`、`GET /repos/{owner}/{repo}/contents/{path}`

| 字段 | 中文含义 | 类型 | 建议字段 | 用途 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `type` | file/dir/symlink/submodule | string | `source_kind` | 过滤 | 分支处理 |
| `name` | 文件名 | string | `name` | RAG metadata | 不可信路径 |
| `path` | 仓库相对路径 | string | `source_path` | RAG filter | 不映射成本地路径 |
| `sha` | Blob/Tree SHA | string | `content_sha` | 增量同步 | 内容身份 |
| `size` | 字节数 | integer | `size_bytes` | 安全过滤 | 先检查再解码 |
| `encoding` | 编码 | string | `encoding` | 解码 | 不假定永远 base64 |
| `content` | 编码内容 | string/null | 受控存储 | RAG | 大文件可能无内容 |
| `download_url` | 下载链接 | string/null | 临时使用 | 获取 | 会过期，不持久依赖 |
| `html_url` | GitHub 页面 | string/null | `github_url` | Citation | 证据链接 |

## Rate Limit

来源：响应头、`GET /rate_limit`

| 字段 | 中文含义 | 类型 | 建议字段 | 备注 |
| --- | --- | --- | --- | --- |
| `x-ratelimit-resource` | 额度池 | string | `resource` | 分开管理 core/search/graphql/code_search |
| `limit` | 窗口上限 | integer | `limit` | 随认证方式变化 |
| `used` | 已使用 | integer | `used` | 当前窗口 |
| `remaining` | 剩余 | integer | `remaining` | 调度依据 |
| `reset` | 重置 Unix 秒 | integer | `reset_at` | 转 UTC timestamp |
| `Retry-After` | 等待秒数 | integer | 事件日志 | secondary limit 优先遵守 |

## Stargazer / Star 派生

| 字段/指标 | 来源 | 类型 | 建议 | 算法用途 | 稳定性 |
| --- | --- | --- | --- | --- | --- |
| `stargazers_count` | Repository | integer | 保存到 Snapshot | Momentum/Adoption | AVAILABLE |
| `starred_at` | Stargazer star media type | timestamp | 不作通用采集字段 | 不直接依赖 | 匿名 401；限 admin/collaborator |
| `user.id/login` | Stargazer list | object | 不采为核心能力 | 否 | 权限、隐私、成本高 |
| `star_delta_7d/30d` | AgentRadar Snapshot 派生 | integer/null | 历史足够后计算 | Momentum | 不足必须 NULL |
| `star_growth_7d/30d` | AgentRadar Snapshot 派生 | decimal/null | 防除零、标算法版本 | Momentum | 不可由当前值回推 |

## 禁止误用

- `watchers_count` 与 `stargazers_count` 同义；真正订阅者是 `subscribers_count`。
- `open_issues_count` 包含 open PR，不能当纯 Issue 数。
- Search `total_count` 不代表所有匹配项都可翻页取得；最多前 1,000 条。
- Contributor `contributions` 不是 30 日活跃贡献者数。
- Languages bytes 不是 LOC；Git tags 不是 Releases。
- Contributor Stats 不是完整历史，也不是实时强一致数据。
- Stargazer List 不是公开稳定能力，且不包含已取消 Star 的完整历史。
