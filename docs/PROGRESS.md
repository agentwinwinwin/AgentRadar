# agentGitHub 项目开发进度

> 只记录真实完成和验证的内容。不得因代码已创建而跳过 Sprint 验收。

## 1. 当前项目状态

| 项目 | 状态 |
| --- | --- |
| 当前阶段 | Sprint 15：Production Hardening |
| 当前状态 | `COMPLETED` |
| 当前允许 Sprint | Sprint 15 已完成，停止执行 |
| 下一允许 Sprint | 无；Sprint 15 为当前路线最终阶段 |

### 2026-10-03 — GitHub 开源发布整理

- 保持 Sprint 15 `COMPLETED`，未新增业务 Sprint；重写公开 README，并补充 MIT License、贡献指南、
  安全策略、行为准则、Changelog、Issue/PR 模板与 EditorConfig。
- README 增加来自线上真实运行环境的数据看板、项目发现、项目详情与智能分析截图；截图不包含
  Token、密码、管理员控制台数据或其他敏感信息。
- 扩展 `.gitignore`，明确排除 `.env`、数据库、模型产物、日志、私钥、论文/简历、个人文档生成脚本、
  本地缓存与依赖目录；生产服务器地址及管理员账号记录已匿名化。
- 对实际 Git 暂存内容执行凭据、私钥、联系方式、个人身份和大文件扫描；公开候选内容未发现真实
  Secret 或个人信息。Compose 配置安全校验通过，未执行与文档整理无关的全量业务测试。

### 2026-09-06 — 登录令牌固定三小时过期

- 保持 Sprint 15 `COMPLETED`，未新增业务 Sprint；认证 Token 默认在登录签发后固定 3 小时过期，
  用户持续操作不会延长有效期，再次显式登录会换发新 Token 并重新计时。
- 后端对每个受保护请求校验 Token 签发时间，过期后拒绝并删除；前端保存服务端返回的
  `expires_at`，到期自动清除登录状态，旧版缺少过期时间的本地缓存按无效会话处理。
- 认证相关 Backend 6 项 pytest 与 Ruff、Frontend 会话/登录/导航 7 项 Vitest 通过；未执行与本次
  修改无关的全量测试。

### 2026-08-20 — Celery 评分任务风暴修复

- 线上审计确认 Star Snapshot 正常写入，但旧 `scoring` 队列积压42,198项，其中32,582项为重复
  Alert Evaluation；同仓库相同提醒最多重复排队20次，导致成熟度状态停留在旧评估时间。
- Snapshot/Activity 通过 Redis 15分钟派发键合并同仓库 Trend 请求；链路调整为
  `Trend → Potential/Learning/Enterprise → Alert`，移除 Snapshot、Activity、Trend 的重复 Alert。
- 全库 Alert 兜底由每小时改为每日；Capability/Retention 路由到 `operations`；新增独立
  `celery-scoring` 单并发 Worker，后台 GitHub Worker 不再消费评分任务。
- 发现旧队列仍含历史全量Alert派发器后补充二次保护：积压超过1,000时跳过全量扫描，并使用23小时
  全局派发键合并重复扫描；恢复Worker后队列重新下降，未强制删除任何必要任务。
- 新增派发失败安全释放、重复派发合并测试，并修正一个超过Decimal范围的既有测试夹具。
- 针对性35项pytest、完整242项pytest、Ruff、Django check、Migration drift和Compose config quiet
  通过；生产已部署独立评分Worker，旧队列未强制删除而是幂等自然排空；成熟度即时重算后真实跨度
  更新为2个完整24小时，Snapshot继续写入，重复派发Smoke返回`True/False`。

### 2026-08-20 — 动态Repository采集优先级

- 新增`monitoring-priority-v1.1.0`，不修改Trend/Potential/Forecast算法；使用Watchlist、真实
  OBSERVED增长、Activity、Release、推送新鲜度、高置信确定性评分、CONFIRMED Training Pool和
  ACTIVE模型信号动态升降HOT/NEW/RISING/NORMAL/STABLE/DORMANT。
- Watchlist项目立即HOT；ACTIVE模型高信号至少RISING；训练池最低NORMAL；低模型信号不会停止采样，
  STABLE/DORMANT仍保留最低Snapshot与Activity，避免模型反馈循环和Category覆盖丢失。
- Snapshot成功、Watchlist增删即时重评，Celery Beat每日通过operations全量幂等重评；层级未变化时
  不滑动下一采集时间。生产3,228项目只读模拟为172/208/55/2,109/202/481/1，约195次Snapshot/小时。
- Snapshot有界派发上限由175调整为225，仍受GitHub Core安全保留额度限制；项目规模继续增长时不会
  无界增加并发。完整249项Backend pytest、Ruff、Django check和Migration drift通过，无数据库变更。
- 增加60天真实采样保护期：仅OBSERVED Snapshot首尾跨度可解锁STABLE/DORMANT降频；不足60天最低NORMAL，
  BACKFILLED不得满足门禁，以保证Star增强模型所需的连续真实历史能够积累。
- STABLE/DORMANT改为严格AND门禁：已满60天、30天Star/Fork低增长、Activity低、无Release、无关注、
  非训练覆盖且无高Trend/Potential/ACTIVE模型信号；核心数据为NULL时保持NORMAL，不按0降频。
- 最终完整Backend回归252项通过；生产同步重评3,228个项目、修正989个层级，结果为HOT 173、RISING 54、
  NEW 208、NORMAL 2,792、ARCHIVED 1；OBSERVED跨度不足60天却被降到STABLE/DORMANT的项目为0。
- Snapshot频率按模型数据粒度收敛：HOT 6小时、RISING 12小时、NEW仅创建后7天且每12小时、
  NORMAL及Training Pool每日、STABLE 3天、DORMANT 7天；前端与图表API不变。
- 完整Backend pytest 253项、Ruff、Django check、Migration drift通过并部署生产；重评3,228项目后为
  HOT 145、NEW 122、NORMAL 2,960、ARCHIVED 1，预计3,784次Snapshot/天（157.7次/小时），较旧配置
  约下降28%。Training Pool中1,008个NORMAL、90个因关注/真实高增长升为HOT、2个已归档，不存在降频项；
  60天保护期误降频数为0，HTTPS Ready验收通过。

### 2026-08-20 — PM Copilot Intent / Skill 业务覆盖增强

- 保持 Sprint 15 `COMPLETED`，不新增业务 Sprint；未修改Trend、Potential、Forecast、Dataset、
  Model Registry、RAG Embedding或GitHub采集逻辑。
- Intent/Skill由9条扩展为13条：新增普通项目发现、高潜排行、单项目Knowledge问答和可信系统说明；
  新增第17个只读MCP Tool `get_system_help`，不开放任何Agent写权限。
- 趋势/高潜排行支持全局或Category内1～20项；Learning/Enterprise不再强制Category，候选列表默认
  10项，深入Evidence仍只取前三项以控制延迟和Tool预算。
- 修复会话切换Intent时继承旧Category的问题；`knowledge_query`等上下文只传给声明该参数的步骤，
  不再污染 `search_projects`。
- 新增趋势前十、高潜前十、系统说明、项目Knowledge、参数白名单、会话约束隔离等回归测试。
- Backend全量pytest、Ruff、Django check及Migration drift全部通过；本次没有Frontend或数据库结构变更。
- 已同步生产并重建Backend/三个Worker/Beat；公网live/ready通过，PostgreSQL/Redis/LLM配置正常，
  三个Worker均pong。真实DeepSeek问题“趋势前十的项目有哪些”路由为`TREND_DISCOVERY` →
  `trend-research`，1次只读Tool返回10个真实项目且状态`COMPLETED`，未输出或记录Secret。

### 2026-08-19 — Star增强预测版本冻结与滚动成熟度

- Star增强百分位改为按 ACTIVE 模型版本冻结：日常 Snapshot/Activity 采集继续，但不会让预测过期
  或自动改写高潜力评分；只有新模型重新训练并由管理员人工激活后，才触发一次全库批量预测。
- 模型激活只退役同一模型家族，避免 Star增强模型与开发活跃度二分类模型互相错误退役。
- Model Registry 新增激活时间、预测发布状态/统计、下一轮训练门槛；批量预测使用 ML Celery Task、
  Redis版本锁与数据库UPSERT保持幂等。输入不足项目回退确定性Potential，不伪造分数。
- 首次门禁仍为60/200/200/3；首次激活后自动切换为更高的“下一次再训练”目标，采集持续积累，
  达到门禁也只允许管理员主动重新训练和激活。
- ACTIVE模型发布后，新项目首次形成可靠`feature-v2.0.0`输入时，由每日成熟度检查分批补做一次
  当前模型预测并冻结；重复检查不覆盖，同一项目无需等待下一次模型训练才获得首次预测。
- 验证：Backend 224项 pytest、Ruff、Django check、Migration drift 全部通过；Frontend 28项
  Vitest、ESLint、TypeScript type-check 与 production build 全部通过。

### 2026-08-19 — 二分类 Forecast 详情页按需预测

- V1开发活跃度二分类模型不做全库批量发布：项目详情页先读当前模型版本结果；缺失且Feature可用时
  通过Redis短期去重投递ML Celery任务，立即返回PENDING，前端每1.5秒短暂刷新，READY后展示。
- 同一模型版本结果持久化复用，日常采集不会自动重算；只有管理员激活新模型版本后才生成新版本预测。
  推理不调用GitHub、不阻塞详情API，Feature不足时继续显示数据不足。

### 2026-08-19 — Dashboard 排行榜紧凑展开

- 数据看板“趋势领先项目”和“高潜力项目”默认各展示前5项；数据超过5项时显示独立的小型展开按钮，
  可分别展开接口已返回的其余项目并随时收起，不影响Dashboard缓存或人工刷新。
- 展开控件使用纯文字“展开全部 / 收起全部”，收起时完全隐藏榜单，展开时展示接口返回的完整榜单，
  默认状态为展开；收起状态不渲染空表或“暂无符合条件”占位，同时移除冗余数量文案与三角图标。
- Frontend ESLint、TypeScript、29项Vitest与production build全部通过。

### 2026-08-19 — Star 增强模型高潜展示切换契约

- 保持 Sprint 15 COMPLETED，不新增业务 Sprint；未修改 `potential-v1.0.0` 公式、历史分数或 Evidence。
- Repository Forecast 新增受0～100数据库约束保护的预测百分位字段；分类概率不得冒充百分位。
- 仅 ACTIVE `feature-v2.0.0` 模型的48小时内有效百分位可接管项目摘要、高潜榜、Discover 与详情页
  的“高潜力评分”；无模型、无覆盖或过期时逐项目自动回退确定性 Potential，NULL 不转0。
- API 同时返回评分来源、原确定性分数、预测百分位和采样时间；前端明确标注当前来源，确定性
  Potential Evidence 继续独立展示，保证评分可解释与可审计。
- Backend 全量 pytest、Ruff、Django check、Migration drift，Frontend lint/type-check、26项 Vitest、
  production build 与 Compose config quiet 全部通过。生产 Migration 已应用，九个长期服务运行；
  当前 ACTIVE `feature-v2.0.0` 模型数为0，公网 Dashboard 实测来源仍为
  `DETERMINISTIC_POTENTIAL`，证明本次发布未提前替换现有高潜分数。

### Sprint 15 完成后的产品体验修复

- [x] Repository Detail 增加首屏“返回发现项目”入口；项目详情及公开评论子路由均保持顶部
  “发现项目”导航选中状态，避免进入详情后丢失当前位置反馈。
- [x] Repository Detail 移除容易与未来 Star 增强预测百分位混淆的“潜力评分记录”图表；
  PostgreSQL Potential 历史、Metrics API、Evidence、回退、Alert 与审计数据全部保留。
- [x] Repository Detail 将 Forecast V1 二分类预测改为正式解释卡片并移动至快照/活跃度图表上方；
  READY 时展示 `P(label=1)`、confidence、版本、周期、采样时间及白名单输入快照，NOT_READY 时
  保持真实数据积累提示。端点固定筛选 Activity Forecast V1，禁止 Star 百分位模型误接该卡片。
- [x] 登录状态统一管理、受保护路由验证 `/auth/me`、导航显示用户与退出操作。
- [x] Dashboard 首次结果本地缓存，后续进入即时展示并支持用户手动刷新。
- [x] Repository Detail 增加真实 GitHub 跳转、登录用户幂等点赞与评论，公开只读社区内容。
- [x] Repository GitHub 简介与 Topic 中文本地化，保留原文并以源内容 Hash 持久化缓存。
- [x] Repository Detail 窄屏图表修复图例与横轴日期重叠，星标/复刻及活动图表统一保留安全间距。
- [x] Repository Detail 将点赞与评论提升到首屏，并新增公开分页项目评论页；所有用户评论互相可见，发布仍需登录。
- [x] Discover 项目列表显示当前用户真实“已关注 / 未关注”状态，复用现有个人 Watchlist API。
- [x] 真实业务验收：公共详情与 Community API 200；真实项目 `affaan-m/ECC` 首次中文翻译为
  `TRANSLATED`、二次命中缓存且 GitHub URL 正确；临时用户登录200、首次/重复点赞201/200且计数1、
  评论201并在重新读取后持久化、取消点赞204；验收临时用户及其互动已清理。

### 2026-08-18 — 云服务器迁移与临时 HTTP 上线

- 已部署至云服务器，生产主机地址与目录仅保存在私有运维配置中，不进入公开仓库。
- PostgreSQL、Redis、Model Artifact 使用备份恢复；恢复后 Repository=3,147、Snapshot=3,425。
- PostgreSQL/Redis/Backend/Celery Worker/Celery Beat/Frontend/Reverse Proxy 全部真实运行；数据库与
  Redis 未映射公网端口，Worker 并发按2核4GB服务器限制为2，所有长期服务使用 `unless-stopped`。
- 公网 Frontend、Backend liveness/readiness、项目列表通过；真实临时用户验证登录、项目详情、
  Watchlist 幂等、点赞/评论、Daily/Weekly Report、Celery Alert 和退出，临时测试数据已清理。
- `agentradar.site` 与 `www.agentradar.site` 已解析并签发受信任 TLS 证书；HTTP 自动跳转至
  `https://agentradar.site`，`www` 自动跳转主域名，HSTS、Secure Cookie 与 HTTPS Redirect 已恢复。
- 已安装 systemd Certbot 自动续期 Timer；证书首次有效期至 2026-11-16，续期后自动 reload Nginx。
- Copilot 未执行真实项目 LLM smoke：上线测试授权不等同于授权将项目内容发送至外部模型服务。

### 2026-08-18 — Repository 中文翻译异步化

- Repository Detail 不再同步调用 DeepSeek；缓存缺失立即返回 GitHub 原始简介/Topic 和 `PENDING`。
- 使用内容 Hash + Redis 10分钟派发键幂等投递 `repositories.localize_repository` 到 knowledge queue；
  Worker 复用原有结构化翻译与持久化缓存，源内容变化时旧任务安全跳过。
- Vue Detail 每3秒轻量轮询项目详情，翻译完成后自动替换中文，最多20次并在页面卸载时清理 Timer。
- 后端本地化/API 16项测试、Ruff、Django check/Migration drift及前端详情2项测试、ESLint、
  TypeScript与Production Build通过；生产运行验收记录在本次部署结果中。
- 真实生产项目 ID=3 首次详情在1.14秒返回 `PENDING` 原文；knowledge queue Worker 的 DeepSeek
  翻译独立耗时4.27秒并成功写为 `TRANSLATED`，下一次3秒轮询读取正式中文，证明请求未等待 LLM。

### 2026-08-18 — 云端 GitHub 采集与磁盘容量优化

- 保持 Sprint 15 COMPLETED；真实云端认证额度为 Core 5,000/小时、Search 30/分钟，rate-limit
  请求约0.20秒。识别到原每日全量 Activity 对3,146个项目约需34,606次 Search/日，风险过高。
- Activity 改为每小时扫描到期项：HOT/NEW/RISING每日、NORMAL每3日、STABLE每7日、DORMANT每30日；
  每批50且单 Worker每分钟最多1项，Search额度不足时自动暂停。真实2项/分钟验收曾触发Search
  限流，现已按实测收紧，并按GitHub `X-RateLimit-Reset` 安排Retry。
- Snapshot 每小时批量从100调整为175，并按真实剩余Core额度扣除安全保留值后截断；现有分层稳态
  约138次/小时，因此新容量可覆盖稳态并逐步消化积压。
- Compose 全服务增加10MB × 3的Docker日志轮转。云盘当前59GB中使用8.3GB，PostgreSQL Volume
  约225MB，暂不需要删除任何业务历史；Alert/Report/Watchlist Event继续执行既有版本化保留策略。
- Snapshot、Activity、Dataset、Model Registry与用户数据均未删除；仅允许运维清理未引用Image和
  过期Build Cache，严禁清理Docker Volume。
- 用户体验隔离：保持总Celery并发为2，将后台采集/评分Worker收敛为concurrency=1，并新增
  concurrency=1的interactive Worker；Repository中文翻译只进入interactive队列。两个Worker均关闭
  批量预取，后台积压不再阻塞用户触发的翻译，同时没有提高总任务并发或GitHub请求密度。
- 生产真实路由验收：background只订阅后台六个队列，interactive只订阅interactive；项目25缓存翻译
  返回TRANSLATED。新增Worker约占152MiB，总容器内存仍低于1GiB。重建容器后发现Nginx保留旧容器
  地址导致瞬时502，已重启Reverse Proxy恢复，readiness及项目25详情均再次通过；运维文档已固化
  每次重建后的Proxy重启与双Smoke要求。

### 2026-08-18 — V1 Learning / Enterprise 全量评分 Pipeline

- 保持 Sprint 15 COMPLETED，不新增业务 Sprint；保留旧 `learning-v1.0.0` / `enterprise-v1.0.0`，
  新增 RAG 非必需的 `learning-v1.1.0` / `enterprise-v1.1.0`。
- 新增轻量 `repository_assessment_evidence` 与 Migration；只经 GitHubClient 检查根目录、`docs/`、
  `.github/` 白名单路径，NULL 与“确认不存在”严格区分，不下载源码或创建 Embedding。
- 新增有界可续跑 Learning/Enterprise Dispatcher、单仓库 Redis Lock、有限 Retry、版本化 UPSERT、
  Rate Limit 保留额度与每日 enrichment；Repository 新发现、Knowledge 完成及 Trend 成熟会自动重算。
- 真实 GitHub smoke 选择25个、覆盖12个 Category：24成功、1失败、53次 Contents 请求、0 Retry，
  耗时133.74秒；失败项保留未确认状态，没有写成不存在或0。
- 全部3,081个有效非 Fork Repository 已生成两个 v1.1 Score：Learning/Enterprise 均非NULL=3,081、
  NULL=0、高置信=73、低置信=3,008；平均 confidence 分别0.3107、0.3266。低置信仅显示
  “数据积累中”，不进入正式 confidence-gated 排名。
- 当前主要缺失为 Activity/Community/Delivery（结构化 Activity、Contributor、Release 覆盖仍低），
  以及尚未轻量检查的 Documentation/Security/Architecture；这些维度保持 NULL，不按0扣分。
- 真实 Celery 顺序重复评分记录 ID 不变，Worker pong；Backend 198项 pytest、Ruff、Django check、
  Migration drift，以及 Frontend 19项 Vitest、lint、type-check、build 全部通过。
- Trend、Potential、Forecast V1、Dataset、Model Registry、Snapshot、RAG版本和 Repository Pool 未修改。

### 2026-08-19 — 管理员生产决策控制台

- 保持 Sprint 15 COMPLETED，不新增业务 Sprint；复用 Django `is_staff` 和既有
  `ModelActivationService`，没有建立平行权限或评分逻辑。
- `/auth/login`、`/auth/me` 返回 `is_staff`；普通用户前端无入口且管理 API 强制403。管理员可查看
  依赖状态、Capability 成熟度、Forecast 状态、Model Registry、Dataset Gate、Validation/Test、
  Feature Importance、Artifact SHA-256 和激活阻塞原因。
- 模型激活要求手工输入完整 model_version；Backend 在事务内再次验证 VALIDATED、Dataset Gate 与
  Validation/Test Precision/Recall/F1/PR-AUC 门槛。仍禁止自动 ACTIVE，未增加训练、删除数据、修改
  Token 或绕过门禁操作。
- 新增 Backend 权限/读取/确认/激活测试和 Frontend 管理员入口/确认测试；前端26项测试、ESLint、
  TypeScript、Production Build及相关后端测试、Ruff、Django check、Migration drift通过。
- 生产管理员账号已提升为 `is_staff=true`、保持 `is_superuser=false` 且密码未修改。真实验收：
  管理员Control Center=200、普通用户=403、错误model_version确认=400、四条Model Registry状态前后
  完全一致、Forecast仍无ACTIVE模型；线上readiness与`/admin` SPA均通过。

### 2026-08-19 — 管理员模型训练工作流

- 保持 Sprint 15 COMPLETED；控制台新增门禁检查、精确确认启动、持久化训练历史与状态轮询。
- 新增 `model_training_runs` 与 Migration；数据库部分唯一约束和 Redis token lock 保证最多一个在途
  训练，失败信息脱敏且不保存 Secret。
- 新增 concurrency=1、1 CPU 的独立 ML Worker；训练继续使用真实 Dataset 和既有三模型比较，完成
  最多为 VALIDATED，禁止自动 ACTIVE。
- 后端测试、Ruff、Django check、Migration drift以及前端26项测试、lint、type-check、build通过；生产
  Migration与独立ML Worker已上线。真实门禁为label-v1.2.0、Dataset Gate/Time Split均PASS，切分为
  156/78/21，管理员200、普通用户403；未自动发起训练，Training Run=0、ACTIVE Model=0。

### 2026-08-19 — Star增强模型数据积攒进度

- 管理员控制台区分现有“开发活跃度模型（不含历史Star）”与未来Star增强模型，避免误以为当前四个
  Model Registry记录使用了历史Star。
- 新增真实快照跨度、60天有效Repository、Star增强Training Sample、Category覆盖与最早标签日期；
  只读取`OBSERVED` Snapshot，Feature需要60天历史且Label还需之后30天真实Activity。
- 修正FORECAST_V2门禁：旧`feature-v1.0.0/label-v1.2.0`样本不再错误计作Star增强样本，正式要求
  `feature-v2.0.0/label-v2.0.0`。当前只展示真实积累，不训练、不激活、不替换Forecast V1。

Sprint 8 已使用真实 Historical Dataset 通过 Quality Gate，完成三分类模型、Percentile Regression
和 Learning Curve。所有模型最多为 VALIDATED，未激活生产 Forecast；本次停止，未进入 Sprint 9。

Sprint 8.5 已建立持续发现、统一到期 Snapshot dispatcher、自适应 Monitoring Tier 与真实
Star/Fork 时间序列积累。ACTIVE Model=0、Forecast=NOT_READY 保持不变；本次禁止进入 Sprint 9。

## 2. Sprint 总进度

| Sprint | 名称 | 状态 |
| --- | --- | --- |
| Sprint -1 | GitHub 数据能力验证 | COMPLETED |
| Sprint 0 | 工程基础设施 | COMPLETED |
| Sprint 1 | Repository Domain | COMPLETED |
| Sprint 2 | Snapshot Pipeline | COMPLETED |
| Sprint 3 | Activity Intelligence | COMPLETED |
| Sprint 4 | Trend Engine | COMPLETED |
| Sprint 5 | Dashboard | COMPLETED |
| Sprint 6 | Potential Engine | COMPLETED |
| Sprint 7 | Historical Dataset | COMPLETED |
| Sprint 8 | Machine Learning Forecast | COMPLETED |
| Sprint 8.5 | Continuous Discovery & Adaptive Snapshot Monitoring | COMPLETED |
| Sprint 9 | Knowledge + RAG | COMPLETED |
| Sprint 10 | Learning / Enterprise Score | COMPLETED |
| Sprint 11 | Tool Layer + MCP | COMPLETED |
| Sprint 12 | Skill Engine | COMPLETED |
| Sprint 13 | PM Copilot Agent | COMPLETED |
| Sprint 14 | Watchlist / Alert / Report | COMPLETED |
| Sprint 15 | Production Hardening | COMPLETED |

允许状态：`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`COMPLETED`。

## 3. Sprint 0 已完成

- [x] 建立 Monorepo 基础目录和根配置。
- [x] 建立 Python 3.12+ Django 5.2 / DRF 后端。
- [x] 建立 Celery 配置，Redis 同时作为 broker/result backend。
- [x] 建立 PostgreSQL 16 + pgvector、Redis、Backend、Celery Worker、Celery Beat、Frontend 的 Docker Compose 定义。
- [x] 建立 Vue 3 + TypeScript + Vite + Pinia + Vue Router + ECharts 前端。
- [x] 建立 pytest、pytest-django、Ruff、ESLint、vue-tsc、Vitest 和 production build 命令。
- [x] 建立后端基础 health endpoint 与测试；未实现业务 API。
- [x] 建立 `.env.example`、`.gitignore`、Makefile、Dockerfiles、Nginx SPA/proxy 配置。
- [x] 创建 `ARCHITECTURE.md`、`DATABASE.md`、`SECURITY.md`、`TESTING.md`。
- [x] 生成 `frontend/package-lock.json`。
- [x] 执行 Django built-in migrations，`makemigrations --check --dry-run` 无变更。
- [x] 本地全量测试和静态检查通过。

## 4. Sprint 0 运行验收

- [x] `docker compose config --quiet` 通过。
- [x] 执行 `docker compose up --build -d`，镜像构建和启动成功。
- [x] postgres、redis、backend、celery-worker、celery-beat、frontend 六个容器均正常运行。
- [x] PostgreSQL `pg_isready` 和 `SELECT 1` 通过；Django built-in migrations 在 PostgreSQL 容器环境成功应用。
- [x] Redis `PING` 返回 `PONG`。
- [x] Backend Health API 返回 `status: ok`。
- [x] Frontend Nginx 代理访问 Backend Health API 返回 `status: ok`。
- [x] Celery Worker 连接 Redis 后进入 `ready`，`inspect ping` 返回 `pong`；Celery Beat 正常启动。

Sprint 0 Definition of Done 已满足；本次停止，未进入 Sprint 1。

## 5. Sprint 1 已完成

- [x] 建立 `GitHubClientProtocol`、`RealGitHubClient` 和 `FakeGitHubClient`。
- [x] GitHub Repository 获取与 Search 统一通过 GitHubClient；未增加旁路 HTTP。
- [x] 固定 REST API version，处理输入、404、限流、网络和非法 JSON 错误。
- [x] 建立 Repository 当前态模型、V1 Category 枚举、Topic 与唯一中间关系。
- [x] 建立 16 条可管理 Discovery Query Pool 数据 Migration。
- [x] 实现 Search 分页上限、不完整/截断标记、fork/archive 防御过滤。
- [x] 实现 Repository create/update，使用 `github_id` 幂等更新并同步 Topic。
- [x] 更新时保留已有 Category，支持 Django Admin 人工分类。
- [x] 提供 `discover_repositories` 与 `sync_repository` 管理命令。
- [x] 新增 GitHubClient、分类、Repository Sync、Discovery 和数据库约束测试。
- [x] 三条 Migration 在 PostgreSQL Compose 环境真实应用，四张业务表存在。
- [x] Sprint 0 Health、Frontend 代理、Celery、PostgreSQL、Redis 与六服务保持正常。

Sprint 1 没有创建 Snapshot、Activity、Contributor、Release、Score 或 Celery 采集任务，也没有开始 Sprint 2。

## 6. Sprint 2 已完成

- [x] 建立 `repository_snapshots` 与6小时 UTC `snapshot_bucket`。
- [x] 建立 `UNIQUE(repository_id, snapshot_bucket)` 数据库约束。
- [x] Snapshot Service 使用 `update_or_create` UPSERT；同桶执行10次只产生1行。
- [x] GitHub 获取统一通过 GitHubClient，Repository 更新与 Snapshot 写入处于同一事务。
- [x] 后续 `snapshot_persisted` 仅通过 `transaction.on_commit` 触发。
- [x] Snapshot/current Repository 可空计数字段保持 NULL，不转换为0。
- [x] 建立 `data_completeness` 与数据库 `[0,1]` Check Constraint。
- [x] 建立 Redis `SET NX EX` repository lock、300秒 TTL 与 token-safe Lua release。
- [x] 锁冲突、GitHubClient 和 Database 暂态错误使用有限 Celery Retry。
- [x] 建立单 Repository Snapshot Task、Beat dispatcher 和6小时调度。
- [x] `github_normal` 路由与 Compose Worker 消费队列真实验证。
- [x] 新增单元、集成、幂等、锁竞争和数据库约束测试。
- [x] PostgreSQL Migration/约束、10次真实 UPSERT、真实 Redis 双竞争者与 Celery broker/worker 链路通过。

Sprint 2 没有实现 Commit/PR/Issue/Contributor/Release 或 Activity Metrics，没有开始 Sprint 3。

## 7. Sprint 3 已完成

- [x] 建立 `repository_activity_metrics` 与 `UNIQUE(repository_id, metric_date)`。
- [x] Commit 7/30/90 天、PR 创建/合并 7/30 天、Issue 创建/关闭 7/30 天均使用已验证 Search `total_count`。
- [x] Search `incomplete_results=true` 时对应 count 写 NULL，不当作完整值或 0。
- [x] 建立 Contributor、Repository Contributor 与 Release 持久化和唯一约束 UPSERT。
- [x] Contributor Statistics HTTP 202 映射为 pending，并使用 `Retry-After`/60秒默认值有限重试；pending 不产生部分 Metric。
- [x] 计算 active contributors 30d、Release 30/90d、距最近 push/release 天数；NULL 与 0 分离。
- [x] Community Profile 当前健康度同步至 Repository。
- [x] Activity Task 使用 repository Redis Lock，Beat 每日派发至 `github_normal`。
- [x] 新增单元、集成、幂等、锁竞争、202 Retry、incomplete Search 测试。
- [x] 公共 GitHub API smoke、PostgreSQL Migration/约束/重复 UPSERT 与 Compose 六服务回归通过。

Sprint 3 未实现 Trend Score、Hype Risk、Potential Score 或 Sprint 4 内容。

## 8. Sprint 4 已完成

- [x] 创建缺失的 `docs/TREND_ENGINE.md`，固化 `trend-v1.0.0` 公式、阈值和 NULL 规则。
- [x] 实现 category + age cohort 及 tie-aware average-rank Percentile。
- [x] 实现 Momentum、Development、Community、Delivery、Adoption、Maintenance 纯 Python 评分。
- [x] 历史不足时 Snapshot 增长保持 NULL，并按组件权重降低 `data_completeness`。
- [x] Topic Momentum 因无真实 Category/Topic 历史保持 NULL，不伪造，完整度相应降低。
- [x] Hype Risk 仅在 30 日 Star/Fork 历史及完整 Development/Community 输入存在时计算。
- [x] 实现确定性 Lifecycle 规则、`algorithm_version` 与结构化 Evidence。
- [x] 建立 `repository_trend_scores`、版本唯一约束及完整度 Check Constraint。
- [x] Snapshot/Activity 成功持久化后派发 `trends.calculate_trend_score` 至 `scoring` 队列。
- [x] 新增边界、NULL、极端值、Cohort、Hype、Lifecycle、确定性、幂等和任务测试。
- [x] PostgreSQL Migration/约束/真实 UPSERT、Redis、Celery scoring 和六服务回归通过。

Sprint 4 未实现 Dashboard/API、Potential Score 或 Sprint 5+ 内容。

## 9. Sprint 5 已完成

- [x] 实现 Dashboard API，返回项目统计、Top Trend、Breakout、High Hype、Lifecycle 与 Category 汇总。
- [x] 实现 Project Discover API，支持搜索、分类、语言、License、Star、Trend、Lifecycle、排序与分页。
- [x] 实现 Project Detail、Metrics 和 Trend API；所有读取均来自 PostgreSQL。
- [x] Trend API 只投影 Sprint 4 持久化结果，保留 `algorithm_version`、`data_completeness` 与 Evidence。
- [x] JSON 与 Vue 全链路严格保留 NULL；UI 显示“数据不足”，真实 0 仍显示为 0。
- [x] Hype 数据不足显示 `INSUFFICIENT_HISTORY`，不伪造风险值。
- [x] Vue 实现 Dashboard、Discover、Repository Detail 和响应式导航。
- [x] 使用 ECharts 展示 Snapshot、Activity 与 Trend 时间序列，并提供 Score Evidence / Why 展示。
- [x] 前端统一调用 `/api/v1` Backend API，不包含 GitHub 请求或 GitHub Token。
- [x] 明确拒绝 Potential/Learning/Enterprise 未来评分筛选；未实现 Potential、Forecast 或 Sprint 6+ 功能。
- [x] 新增后端 API 与前端组件/页面测试；全量测试、Lint、类型检查、Django check、Migration drift 与 Compose smoke 通过。
- [x] Compose 配置验证改用 `docker compose config --quiet`，不输出解析后的 Secret。

Sprint 5 没有数据库 Schema 变更，因此没有新增 Migration。Sprint 4 保持 COMPLETED；未开始 Sprint 6。

## 10. Sprint 6 已完成

- [x] 补齐缺失的 `docs/POTENTIAL_ENGINE.md`，固化 `potential-v1.0.0` 公式、confidence、NULL、Hype 与候选规则。
- [x] Potential 为纯 Python 确定性评分，只复用 Sprint 4 持久化 Trend/组件/Hype，不调用 GitHub、LLM 或模型。
- [x] Topic Momentum 因无真实历史保持 NULL；Novelty 因无规范化可验证数据源保持 NULL，不以常量或年龄伪造。
- [x] 可用分量按主规范权重归一化；缺失分量不当 0，并按原始权重与组件完整度降低 confidence。
- [x] Hype Risk 缺失时 penalty=0，confidence 乘 0.85；Hype 可用时按 `HypeRisk * 0.15` 扣分。
- [x] 实现 High Potential、Potential Candidate、Breakout Candidate 多信号门槛与可解释 Ranking。
- [x] 小项目仅有高百分比 Momentum 时无法通过多信号候选与 confidence 门槛。
- [x] 创建 `repository_potential_scores`、算法版本唯一约束和 confidence `[0,1]` Check Constraint。
- [x] Potential 重复计算使用 UPSERT；Trend 成功持久化后才派发 Potential scoring task。
- [x] 新增 Potential API、Dashboard 高潜榜/突破候选、Discover 筛选排序、Detail/Metrics 投影。
- [x] Vue 增加 Potential、confidence、候选状态、历史图表和“为什么获得这个潜力评分”Evidence。
- [x] 未实现 Historical Dataset、训练模型、Forecast Probability、RAG、MCP、Skill 或 Agent。
- [x] 69 项后端、7 项前端测试及全部工程门禁通过；PostgreSQL/Redis/Celery/API/UI Compose 验收通过。

Sprint 6 已完成并停止；Sprint 7 Historical Dataset 保持 NOT_STARTED。

## 11. Sprint 7 已完成

- [x] 补齐 `docs/DATASET.md` 与 `docs/FORECAST_ENGINE.md`；Forecast 明确保持 NOT_READY。
- [x] 建立 `historical_activity_windows`，所有历史 GitHub Activity 回填标记 `BACKFILLED`。
- [x] Feature 使用 T-6..T 与 T-29..T；Label 使用严格晚于 T 的 T+1..T+30。
- [x] Feature V1 实现总规范字段；无可靠历史的 Star/Fork/Push/Community/Topic 保持 NULL。
- [x] Label V1 使用 Commit、PR、Contributor、Release、Issue Resolution 五项同权 Cohort Percentile。
- [x] Label 五项任一 NULL 时跳过样本，不把不完整 Label 当负样本；Top 20% 为 label=1。
- [x] Category + Age Cohort 隔离与 tie-aware Percentile 已测试；Sprint 8 后续增加最小 Cohort 门禁。
- [x] Training Sample 保存 feature/label version、窗口、来源、Feature provenance 与 Label Evidence。
- [x] 同 Repository 支持多个 sample_at；同 sample/version 使用 UPSERT，重复构建不重复。
- [x] 自动 Data Leakage Guard 拒绝未来 Feature timestamp、Label 重叠和 repository_id Feature。
- [x] Dataset Quality 输出正负比例、Category/Age 分布、时间范围、缺失率和版本分布。
- [x] GitHubClient 处理真实大响应 `IncompleteRead` 为可重试错误；Contributor Stats 202 不写部分窗口。
- [x] Worker 增加 `github_backfill` 队列，注册 Backfill 与 Dataset Builder task；不加入 Beat。
- [x] 真实 `octocat/Hello-World` 回填三窗口成功；Builder 两次为 created=1/updated=1，样本 count=1。
- [x] 真实回填仓库 Snapshot count=0，确认没有伪造历史 Star Snapshot。
- [x] 未训练 Logistic Regression、Random Forest、XGBoost，未实现 Forecast Probability 或 Sprint 8+。

Sprint 7 完成时 Sprint 8 尚未开始；当前 Sprint 8 状态见下一节。

## 12. Sprint 8 已实现但数据门禁阻塞

- [x] 正式 Label Cohort 最小完整候选数配置为 20；测试可显式使用 5，正式运行不得降级。
- [x] Dataset Quality Gate 检查规模、正负数量/比例、Category、Age Cohort、核心 Feature 缺失率、
  时间范围、版本与 BACKFILLED provenance。
- [x] 实现按 sample_at 的 70%/15%/15% Training/Validation/Test，禁止同时间点跨 Split，三段均需正负 Label。
- [x] 实现 Logistic Regression、Random Forest、XGBoost CPU 三模型训练与完整指标。
- [x] 模型选择以 Validation PR-AUC、F1、Precision 为优先级，不以 Accuracy 单独决策。
- [x] 建立 Model Registry、artifact SHA-256、Feature Importance、显式激活阈值与 ACTIVE/RETIRED 生命周期。
- [x] 模型训练后只进入 VALIDATED，绝不自动 ACTIVE；低指标模型无法激活。
- [x] 建立幂等 Forecast 持久化、`ml` Celery queue、Forecast API 与中文 NOT_READY UI。
- [x] Forecast 定义固定为“未来30天进入同 Category 高开发活跃增长组的概率”；Age Cohort保留为Feature。
- [x] 单元测试构造数据只验证三算法代码路径，不作为产品模型效果证据。
- [x] 真实 PostgreSQL 重跑 smoke Cohort：eligible=1、skipped_small_cohort=1、有效样本从 1 变为 0。
- [x] 真实训练命令被 Quality Gate 拒绝；ml_models=0、ACTIVE=0、repository_forecasts=0。
- [x] Compose 六服务、Migration、ml queue、Backend/Frontend Health 与 Forecast fallback 真实通过。
- [x] 获取足够真实 Historical Dataset 并通过 Quality Gate。
- [x] 在真实 Dataset 上训练、Validation、独立 Test 并记录三模型真实指标。
- [x] 满足指标的模型仅登记 VALIDATED；按本轮要求不执行管理员激活。

以下 Phase E 记录是当时的历史阻塞点；最终状态由后续“Targeted Backfill、真实训练”章节覆盖。

### Phase E Batch B 安全暂停与 Label v1.2 评估

- [x] Batch B 自然结束后暂停 Historical Backfill，未启动 Batch C；28/30 Repository 完成，
  2 个因 GitHub Rate Limit 失败，未绕过限流。
- [x] Batch B 创建 234、复用 18 个 Bucket；API 933（Search 862、Core 71），transport retry 7、
  Contributor 202 wait 9、Rate wait 29；最终 Search remaining 25、Core remaining 208。
- [x] 暂停点 Bucket 总数 746；PostgreSQL transaction status=IDLE，残留 RUNNING Item=0，
  backend 无残留 Backfill 管理进程。已有 Bucket 与业务数据未删除、重置或覆盖。
- [x] 新增 `label-v1.2.0` 兼容设计：显式保存未来 Activity Percentile、由 >=80 唯一派生的
  binary Top 20% Label 及 Cohort Size；v1.0/v1.1 保持不变。
- [x] Migration 0008 仅新增可空字段与 Check Constraint，真实 PostgreSQL 应用成功。
- [x] 对 800/1,000/1,200/1,500 运行纯本地 Cohort Simulation；四种规模均覆盖 11 Category，
  >=20 Cohort 为 40，>=50 为 20，>=80 分别为 14/16/16/16。
- [x] 复用现有 746 Bucket 本地验证：74 Repository、296 候选，Label 不完整 27、Cohort 不足
  269，`label-v1.2.0` percentile/binary 均为 0；未请求 GitHub、未训练模型。
- [x] Dataset 定向单元测试 17 项、后端全量 115 项通过；Ruff、Django check、Migration drift
  通过。
- [x] 人工决策保持 Training Pool 800，并改用三个主要 Category 的 Targeted Backfill。

此处为设计评估时的历史状态；后续 Targeted Backfill 已解除 Dataset 阻塞。

### Targeted Backfill、真实训练与 Sprint 8 完成

- [x] 决策保持 Candidate 3,081、Training Pool v2 800 CONFIRMED；未扩大 Pool、未执行 Discovery。
- [x] GitHub 请求前两次真实 Rate Limit 均确认 Core=5,000、Search=30，未沿用旧额度。
- [x] 仅对 Framework/Multi/Coding 运行两批 Targeted Backfill（30 + 24 selection），已有 Bucket
  全部复用；Batch 1 成功27/失败3，Batch 2成功17/失败7。
- [x] 两批创建396 Bucket，总数1,142；API合计1,626（Search 1,465、Core 161），transport
  retry 24、Contributor 202 wait 39、Rate wait 41，未绕过限流。
- [x] label-v1.2.0 生成255个真实样本：正37、负218、正样本率14.5098%；Category=3、
  Age Cohort=4、sample_at=4、跨度90天，最大核心Feature缺失率41.5686%。
- [x] Dataset Quality Gate 全部PASS；Time-based Training/Validation/Test 为156/78/21，正负分别
  20/136、12/66、5/16，三段均同时含正负样本，触发Early Stop，未启动第三批。
- [x] 真实训练 Logistic Regression、Random Forest、XGBoost；Validation优先选择XGBoost。
- [x] Percentile Random Forest Regression baseline 完成；Validation MAE=7.398464、RMSE=10.950757、
  R²=0.780253，Test MAE=9.123770、RMSE=11.617011、R²=0.802402。
- [x] XGBoost Learning Curve Validation PR-AUC：25%=0.741725、50%=0.842520、75%=0.887436、
  100%=0.908350，记录 `MORE_DATA_LIKELY_BENEFICIAL`；本轮仍按Early Stop停止采集。
- [x] 四个model artifact存入持久化`ml_artifacts` Volume，存在性及SHA-256全部通过；Feature
  Importance使用业务字段名，不保留x0内部名称。
- [x] 四个Registry记录均为VALIDATED，ACTIVE=0、Forecast rows=0，产品状态保持NOT_READY。
- [x] 后端全量117项、Ruff、Django check、Migration drift全部PASS；Compose配置quiet检查、
  六服务、双Health、Celery pong及共享artifact Volume真实验收通过。

Sprint 8 Definition of Done 已满足并标记 `COMPLETED`。下一允许 Sprint 为 Sprint 9，但本次严格
停止，未实现或启动任何 Sprint 9 内容。

### Dataset Acquisition / Sampling 补充

- [x] 保留原有 824 个 Repository 及全部 Snapshot/Activity/Trend/Potential 数据，未清空或重置。
- [x] 完成 Category、Star Bucket、Age Cohort、Activity Level Coverage Audit；Activity 为
  UNKNOWN 823/824，是当前主要覆盖缺口。
- [x] 对 10 个主要 Category 执行 Star Top 10 Head Coverage：初始 88/100，复用 88、补入 12，
  最终 100/100；Repository 总数 836。
- [x] 只针对成员少于 5 的组合建立 Category + Star + Created-date Query Shard，未重复全量 Discovery。
- [x] 有界执行 5 个最高短缺 Shard：seen=5、reused=5、created=0；最终 active shard=55。
- [x] Migration 建立 CANDIDATE/TRACKED/TRAINING Pool、Membership 与 DRAFT/CONFIRMED Guard。
- [x] Candidate Pool=836、Tracked Pool=509；Training Pool 使用 Category + Star + Age 分层选择 300，
  不按 Star 简单排序。
- [x] DRAFT Training Pool 被 Backfill 命令真实拒绝；审计后显式确认 `sprint8-training-v1`。
- [x] 本阶段未恢复大规模 Historical Backfill，Sprint 8 继续 BLOCKED，未进入 Sprint 9。
- [x] 停止的旧 Backfill 批次标记 PARTIAL，2 个中断 Item 恢复 PENDING；239 个已写
  BACKFILLED Window 与全部检查点保留。
- [x] Dataset Acquisition 定向测试 24 项、优化后全量后端 104 项、Ruff、Django check、Migration
  drift：PASS；前端 7 项与 production build：PASS。
- [x] Compose 六服务运行，PostgreSQL/Redis healthy，Backend 与 Frontend proxy Health：PASS。

### Historical Dataset Acquisition 优化

- [x] 按用户要求暂停 legacy 14 天首批，不再扩大；暂停时 50 仓库/450 Item 中 succeeded=98、
  pending=352、failed=0，完整仓库=10。已写 BACKFILLED 数据和检查点全部保留。
- [x] 实测 legacy 批次累计 Commit Search=294、PR Search=589、Issue Search=588，确认相邻
  7/30/30 日窗口存在高重叠请求。
- [x] 建立 `activity-bucket-v1.0.0` / `monthly-sampling-v1.0.0`：最近 6～12 个月、精确
  30 天 sample 间隔、连续 30 日桶复用及 7 日 Commit/PR 尾桶。
- [x] Contributor Statistics 周统计与 Release 日期每仓库一次采集后持久化，本地组合窗口。
- [x] 新增 Dataset Early Stop：Quality Gate 通过且 time-based Train/Validation/Test 均含正负样本。
- [x] N=10 估算每仓库请求 152→77，100 仓库 15,200→7,700，减少 49.34%，最多产生
  1,000 个候选样本。
- [x] 6/12 个月边界估算：每仓库 92→49 / 182→91；100 仓库 9,200→4,900 /
  18,200→9,100；候选 Sample 600 / 1,200。
- [x] 按要求完成优化与测试后停止，没有继续大规模 Backfill，没有训练模型或进入 Sprint 9。

### Activity Bucket 20 Repository 真实验证

- [x] 仅从 `sprint8-training-v1` CONFIRMED Pool 分层选择 20 个历史上符合条件的 Repository；
  覆盖 4 个 Category、4 个 Star Bucket 和 3 个 Age Cohort，没有调用旧 Backfill 路径。
- [x] 使用 `activity-bucket-v1.0.0` 与 `monthly-sampling-v1.0.0`，2026-02-17 至
  2026-07-17 共 6 个精确 30 天 sample_at；20/20 成功、0 失败，创建 260 Bucket。
- [x] 真实 GitHub API 请求 992：Search 941（Commit 260、PR 401、Issue 280），Contributor
  Statistics 30，Release 21；Retry/Rate wait 42，最终 Search remaining=20、Core remaining=4949。
- [x] 总耗时 1979.790 秒；平均每 Repository 49.60 次 API、47.05 次 Search、13 个 Bucket。
- [x] 生成 120 个候选 Sample；6 个因 Label 数据不完整排除，114 个因正式 Cohort 最小成员数
  20 排除；有效 Sample=0，正/负样本均为 0，没有降低门禁或训练模型。
- [x] 候选 Activity Feature 缺失率：Commit/PR/Issue/Release=0%，active contributors=2.5%；
  历史 Star/Fork、days since push、Community、Topic Momentum=100%，days since release=58.33%。
- [x] 结构推演显示当前分层 Pool 在相同 6 个月窗口下，100 Repository 和历史起点前已存在的
  181/300 Repository 均无 Category + Age Cohort 达到 20，预计有效 Sample 仍为 0；继续请求 API
  不能解决此门禁结构问题。按实测线性估算，100/300 Repository 约需 4,960/14,880 次 API，
  其中 Search 约 4,705/14,115 次。
- [x] 本次验证完成后停止，没有扩大批次、训练模型或进入 Sprint 9；Sprint 8 保持 BLOCKED。

### Label v1.1.0 本地重建

- [x] 新增 `label-v1.1.0`：Label Cohort 改为同一 `sample_at` 内的 Category，移除 Age Cohort；
  Top 20%、五项 Activity 信号、正式 `MIN_COHORT_SIZE=20` 均保持不变。
- [x] `label-v1.0.0` 保留并可显式构建；新旧版本通过 Training Sample 版本唯一键并存，不覆盖旧数据。
- [x] `repo_age_days` 与 `age_cohort` 继续保留在模型 Feature；Forecast 当前目标 Label 语义同步为
  “未来30天进入同 Category 高开发活跃增长组的概率”。
- [x] 仅使用 PostgreSQL 已有 260 个 `activity-bucket-v1.0.0` Bucket/Window 本地重建，GitHub API
  请求为 0；候选 120，Label 不完整过滤 6，Category Cohort 不足过滤 114，有效样本 0。
- [x] 候选 Category：Framework 48、Memory 30、Security 24、Observability 18；每个 sample_at
  候选 20。因为单日最大 Category 仅 8，仍无法满足 Category Cohort 20。
- [x] 正样本 0、负样本 0。候选 Feature 缺失率与 Bucket 验证一致：Activity 基础计数 0%，
  active contributors 2.5%，days since release 58.33%，无可靠历史来源的 Star/Fork、Push、
  Community、Topic 为 100%。
- [x] Dataset Quality Gate 未通过：total/positive/negative/category/age/time span/sample dates/version/
  historical origin 均因有效样本为 0 失败；修正空 Dataset 时缺失率检查不得误显示通过。
- [x] Dataset/Forecast 相关测试 35 项及后端全量 108 项通过；Ruff、Django check、Migration drift
  通过；前端 lint/type-check、7 项测试及 production build 通过。没有训练模型、恢复 Backfill
  或进入 Sprint 9，Sprint 8 保持 BLOCKED。

## 13. Sprint 9 Repository Knowledge RAG 已完成

- [x] 建立 `knowledge_documents`、`knowledge_chunks`、`knowledge_sync_states` 与 pgvector Migration。
- [x] Embedding Provider 可配置；Pilot 使用本地 `hashing-384` / `embedding-v1.0.0`。
- [x] heading-aware 400～800 token Chunk，75 token overlap，保留标题路径、代码块、列表和表格。
- [x] 文件路径作为稳定身份，`content_hash` Change Detection；未变化内容不重复 Embedding。
- [x] 仅采集 README、最多25个核心 docs Markdown、专项 Markdown 和最近5个非 Draft Release。
- [x] 常规 Pilot 禁用 PR/Issue Search；仅 Smoke 保留2个高价值 PR、7个高价值 Issue。
- [x] pgvector Repository Filter、Category/Source/时间过滤、cosine 检索和可追溯 Evidence。
- [x] Structured Snapshot/Activity/Trend/Potential/Forecast 保持独立 PostgreSQL 查询，不进入 RAG。
- [x] Celery `knowledge` queue、Redis Lock、有限 Retry 和仅维护已准入 Pilot 的 Beat dispatcher。
- [x] Pilot 停止在50个有有效 Knowledge 文档的仓库：302 Document、1,501 Chunk、885,641 Token。
- [x] README 50、核心 Docs 228、Release 15；另有 PR 2、Issue 7。
- [x] 六类真实问题检索、Evidence 字段、Architecture/Release/PR/Issue 覆盖与幂等复验通过。

Sprint 9 未实现全量 Repository Embedding、MCP、Skill、PM Copilot Agent 或 Sprint 10 内容。

## 14. Sprint -1 数据能力状态

详细结论见 `docs/GITHUB_CAPABILITIES.md` 和 `docs/GITHUB_DATA_DICTIONARY.md`。

| 数据 | 状态 | 说明 |
| --- | --- | --- |
| Repository / Search | AVAILABLE | Search 前 1,000 条限制 |
| Commit / PR / Issue | AVAILABLE | 窄时间窗口统计可用 |
| Contributor | AVAILABLE | 当前聚合 |
| Contributor Stats | PARTIAL | 缓存/202、最近 10,000 commits |
| Release / Languages | AVAILABLE | 当前与历史边界已记录 |
| Community Health | PARTIAL | 当前快照、算法可变 |
| README / File | AVAILABLE | 内容不可信 |
| Star 当前数量 | AVAILABLE | 必须自行 Snapshot |
| Star 历史 | UNAVAILABLE | 无完整历史 Endpoint |
| Stargazer List | UNAVAILABLE | 匿名 401；受 admin/collaborator 限制 |

## 15. 已知问题

### ISSUE-001 — Stargazer 授权成功路径未验证

- 当前环境无目标仓库 admin/collaborator token。
- 不影响生产只依赖 `stargazers_count` + 自身 Snapshot 的结论。
- 状态：OPEN。

### ISSUE-002 — 容器运行时缺失

- 问题：当前环境不存在 `docker`、`podman`、`colima`、`orbctl`、`nerdctl`。
- 安装复核：主机为 Intel Mac、macOS 13.7.8；Docker Desktop 当前可下载版本要求 macOS 14+。Docker Desktop 4.48 是最后兼容 macOS 13 的版本，但 Docker 官方不再提供超过六个月的旧版下载。
- 影响：无法执行 Sprint 0 的明确验收 `docker compose up`，不能确认六个容器运行状态。
- 已完成替代检查：Compose YAML 可解析且六个要求服务均存在；不能替代真实启动。
- 2026-08-16 复核：常见 Docker Desktop、OrbStack、Rancher Desktop 应用位置及 Docker CLI 路径均不存在；直接执行 `docker compose config --quiet` 和 `docker compose up --build -d` 均退出 127（`docker: command not found`）。
- 解决结果：macOS 13 无法安装当前 Docker Desktop，已改用兼容 Docker CLI 的 Colima Runtime；安装 Docker CLI 20.10.22、Docker Compose 2.15.0、Colima 0.5.2、Lima 0.14.2、QEMU 7.2.0。
- 运行验证：Colima 使用 QEMU/x86_64 启动成功，Docker client/server 可连接，`docker run --rm hello-world` 拉取并运行成功。
- 状态：RESOLVED。项目 Compose 运行验收已完成。

## 16. 技术债务

### DEBT-001 — GitHubClient 集成规则

- Sprint 1 已完成统一 Client、Search 分页/1,000 条边界、输入/404/限流错误测试及 Fake Client。
- 超过 1,000 条的查询由管理员在 Query Pool 中配置更窄分片；当前结果明确返回 truncated 状态，不声称完整。
- Contributor Stats 202 与 `Retry-After` 有限退避已在 Sprint 3 完成。
- 条件 GET/ETag 尚未实现，属于后续生产限流优化，不影响 Sprint 3 DoD。
- 状态：PARTIALLY RESOLVED；Sprint 1/3 必需范围完成，条件 GET 保持 OPEN。

### DEBT-002 — 容器 CI

- 已增加 `.github/workflows/compose-smoke.yml`，在 push/PR 执行 Compose 配置、构建启动、Health、PostgreSQL、Redis、Celery 和清理验收。
- 已增加 `make compose-smoke` 本地等价入口，并通过真实 Colima Runtime 验证。
- Backend/Frontend `.dockerignore` 已排除本地产物；Frontend 构建上下文由约 172 MB 降至 825 B。
- 状态：RESOLVED。

### DEBT-003 — Topic Momentum 历史

- 当前尚无 Category/Topic Snapshot 历史，Trend V1 不从当前值伪造 Topic Momentum。
- `topic_momentum_score` 保持 NULL，因此 V1 完整度上限为 0.90。
- 待后续明确 Sprint 建立真实分类历史后，通过新 algorithm_version 启用；不回写 v1。
- 状态：OPEN，非 Sprint 4 阻塞项。

### DEBT-004 — Frontend bundle 拆分

- ECharts 与当前页面打入同一入口 chunk，Vite production build 提示压缩后 JS 约 1.24 MB。
- 功能、类型与运行验收均通过；后续可在不改变 API 的前提下按路由懒加载并拆分 ECharts vendor chunk。
- 状态：OPEN，非 Sprint 5 阻塞项。

### DEBT-005 — 历史 Category 分类

- 当前没有 Category Assignment 历史表；历史样本使用当前人工/规则分类并在 provenance 标记
  `category_source=current_classification`。
- 这不引入未来 GitHub Activity 数值，但历史 Category 变更无法复原。后续若建立分类历史，应以新
  `feature_version` 重建，不覆盖 feature-v1。
- 状态：OPEN，非 Sprint 7 Builder 阻塞项。

### DEBT-006 — ML 镜像与运行时

- Linux 使用官方 `xgboost-cpu`，避免标准 XGBoost 拉取 342 MB NCCL/GPU 依赖。
- Intel macOS 本地 XGBoost 需要 Homebrew `libomp`；已真实安装并验证。
- NumPy/OpenBLAS 在 Colima 中报告无法识别 L2 cache，未影响训练路径或 API，但后续生产镜像应评估专用 ML Worker。
- 状态：OPEN，非当前 Dataset Gate 阻塞原因。

## 17. Migration / API / Celery 状态

| 类型 | 状态 | 说明 |
| --- | --- | --- |
| Django built-in migrations | APPLIED_COMPOSE_POSTGRES | admin/auth/contenttypes/sessions；PostgreSQL 容器验证 |
| Repository migrations | APPLIED_COMPOSE_POSTGRES | 0001 domain、0002 stars index、0003 query seed |
| Repository NULL migration | APPLIED_COMPOSE_POSTGRES | 0004 nullable counters；缺失不写0 |
| Snapshot migration | APPLIED_COMPOSE_POSTGRES | snapshots 0001；unique bucket + completeness check |
| Activity migration | APPLIED_COMPOSE_POSTGRES | activities 0001；4 tables + activity/contributor unique constraints |
| Trend migration | APPLIED_COMPOSE_POSTGRES | trends 0001；algorithm unique + completeness check |
| Potential migration | APPLIED_COMPOSE_POSTGRES | potentials 0001；algorithm unique + confidence check |
| Dataset migration | APPLIED_COMPOSE_POSTGRES | datasets 0001；window/sample unique、time/completeness/label checks |
| Forecast migration | APPLIED_COMPOSE_POSTGRES | forecasts 0001；Model Registry、Forecast unique/binary constraints |
| API | SPRINT_8_NOT_READY | Forecast API 已实现；无 ACTIVE 模型时回退 POTENTIAL_SCORE |
| Celery | ML_QUEUE_VERIFIED | Worker 消费 ml；train_models/run_forecast 已注册，不加入 Beat |
| Frontend | SPRINT_8_NOT_READY | Detail 展示 Forecast 定义与真实 NOT_READY 状态 |

## 18. 测试状态

执行日期：2026-08-16。

| 命令 | 结果 |
| --- | --- |
| `cd backend && pytest` | PASS，1 passed |
| `cd backend && ruff check .` | PASS |
| `cd backend && python manage.py check` | PASS，0 issues |
| `cd backend && python manage.py makemigrations --check --dry-run` | PASS，No changes detected |
| `cd frontend && npm run lint` | PASS，0 warnings |
| `cd frontend && npm run type-check` | PASS |
| `cd frontend && npm run test` | PASS，1 test passed |
| `cd frontend && npm run build` | PASS，Vite production build |
| `make test` | PASS，汇总命令全部通过 |
| `python -m pip check` | PASS，No broken requirements |
| Compose YAML 六服务静态检查 | PASS |
| `docker compose config --quiet` | PASS，不打印解析后 Secret |
| `docker compose up --build -d` | PASS，六服务启动 |
| PostgreSQL / Redis | PASS，`pg_isready`、`SELECT 1`、`PONG` |
| Backend / Frontend→Backend Health | PASS，均返回 `status: ok` |
| Celery Worker / Beat | PASS，Worker `ready`/`pong`，Beat `Starting` |
| `make compose-smoke` | PASS，DEBT-002 本地入口完整执行 |
| `cd backend && pytest`（Sprint 1） | PASS，11 passed |
| `cd backend && ruff check .`（Sprint 1） | PASS |
| `cd backend && python manage.py check`（Sprint 1） | PASS，0 issues |
| `python manage.py makemigrations --check --dry-run` | PASS，No changes detected |
| PostgreSQL `showmigrations repositories` | PASS，0001/0002/0003 applied |
| PostgreSQL Sprint 1 表与 Query Pool | PASS，4 tables，16 queries |
| Sprint 1 Compose compatibility | PASS，六服务 Up，Health PASS，Celery pong |
| `cd backend && pytest`（Sprint 2） | PASS，22 passed |
| `cd backend && ruff check .`（Sprint 2） | PASS |
| `cd backend && python manage.py check`（Sprint 2） | PASS，0 issues |
| Sprint 2 Migration drift | PASS，No changes detected |
| PostgreSQL Snapshot Migration/constraints | PASS，unique bucket 与 completeness check 存在 |
| PostgreSQL 同桶连续10次 UPSERT | PASS，count=1；NULL 保持 NULL |
| 真实 Redis 双竞争者 Lock | PASS，`[False, True]` |
| Celery github_normal dispatcher | PASS，Worker 返回 `dispatched` 结果 |
| Sprint 2 Compose compatibility | PASS，六服务 Up，双 Health PASS |
| `cd backend && pytest`（Sprint 3） | PASS，32 passed |
| `cd backend && ruff check .`（Sprint 3） | PASS |
| `cd backend && python manage.py check`（Sprint 3） | PASS，0 issues |
| Sprint 3 Migration drift | PASS，No changes detected |
| 公共 GitHub Activity smoke | PASS，Repository/Search/Contributor/Stats/Release/Community；Search complete=true |
| PostgreSQL Activity Migration/constraints | PASS，activities 0001；activity date/contributor unique constraints 存在 |
| PostgreSQL 同日连续2次 Activity UPSERT | PASS，created=True/False，rows=1 |
| Sprint 3 Compose compatibility | PASS，六服务 Up，双 Health、Redis PONG、Celery pong/Beat PASS |
| `PATH=<Node 24>/bin:$PATH make test`（Sprint 3 全量） | PASS，Backend 32 + Frontend lint/type/test/build |
| `cd backend && pytest`（Sprint 4） | PASS，51 passed |
| `cd backend && ruff check .`（Sprint 4） | PASS |
| `cd backend && python manage.py check`（Sprint 4） | PASS，0 issues |
| Sprint 4 Migration drift | PASS，No changes detected |
| PostgreSQL Trend Migration/constraints | PASS，trends 0001；version unique + completeness check |
| PostgreSQL Trend 连续2次 UPSERT | PASS，created=True/False，rows=1，evidence persisted |
| Celery scoring | PASS，Worker pong，两个 Trend task 注册，worker 消费 scoring |
| Sprint 4 Compose compatibility | PASS，六服务 Up，Redis PONG，双 Health PASS |
| `PATH=<Node Runtime>/bin:$PATH make test`（Sprint 5 全量） | PASS，Backend 58 + Frontend 6；Lint/Type/Build PASS |
| `cd backend && pytest`（Sprint 5） | PASS，58 passed |
| `cd backend && ruff check .`（Sprint 5） | PASS |
| `cd backend && python manage.py check`（Sprint 5） | PASS，0 issues |
| Sprint 5 Migration drift | PASS，No changes detected；本 Sprint 无 Migration |
| `cd frontend && npm run test`（Sprint 5） | PASS，6 passed |
| Sprint 5 production build | PASS，Vite production build |
| Sprint 5 Compose/API compatibility | PASS，六服务 Up；Health、Dashboard、Project APIs、PostgreSQL、Redis、Celery PASS |
| `PATH=<Node Runtime>/bin:$PATH make test`（Sprint 6 全量） | PASS，Backend 69 + Frontend 7；Lint/Type/Build PASS |
| `cd backend && pytest`（Sprint 6） | PASS，69 passed |
| `cd backend && ruff check .`（Sprint 6） | PASS |
| `cd backend && python manage.py check`（Sprint 6） | PASS，0 issues |
| Sprint 6 Migration drift | PASS，No changes detected |
| `cd frontend && npm run test`（Sprint 6） | PASS，7 passed |
| Sprint 6 production build | PASS；仅保留已记录 bundle size warning |
| PostgreSQL Potential Migration/constraints | PASS；potentials 0001、unique algorithm、confidence check |
| 真实 Celery Potential Task 连续2次 | PASS；created=True/False，数据库 count=1 |
| Sprint 6 Compose/API/UI | PASS；六服务 Up，双 Health、Potential API/筛选/Detail、Redis/Celery PASS |
| `PATH=<Node Runtime>/bin:$PATH make test`（Sprint 7 全量） | PASS，Backend 82 + Frontend 7；Lint/Type/Build PASS |
| `cd backend && pytest`（Sprint 7） | PASS，82 passed |
| `cd backend && ruff check .`（Sprint 7） | PASS |
| `cd backend && python manage.py check`（Sprint 7） | PASS，0 issues |
| Sprint 7 Migration drift | PASS，No changes detected |
| Dataset unit/integration/leakage tests | PASS，12 passed；另有 GitHub transport regression |
| PostgreSQL Dataset Migration/constraints | PASS；2 tables，window/sample/version/label constraints |
| Contributor Stats 202 + retry smoke | PASS；pending 无写入，重试后 3 BACKFILLED windows |
| Training Sample 连续2次 Builder | PASS；created=1/updated=1，count=1，版本和来源正确 |
| Dataset Quality smoke | PASS；balance/category/age/range/missing/version JSON 完整 |
| Sprint 7 Compose compatibility | PASS；六服务 Up，Redis PONG，Worker tasks/queue、双 Health PASS |
| `cd backend && pytest`（Sprint 8） | PASS，88 passed；依赖兼容范围固定后无测试 warning |
| `cd backend && ruff check .`（Sprint 8） | PASS |
| `cd backend && python manage.py check`（Sprint 8） | PASS，0 issues |
| Sprint 8 Migration drift / pip check | PASS，No changes detected / No broken requirements |
| Sprint 8 Frontend lint/type/test/build | PASS，7 passed；保留既有 bundle warning |
| Sprint 8 Compose / Forecast smoke | PASS；六服务、forecast migration、ml queue、双 Health、NOT_READY fallback |
| Sprint 8 初始真实 Dataset Gate | FAIL（历史阻塞点）；0 有效样本，未创建模型或 Forecast |
| Sprint 8 最终真实 Dataset Gate | PASS；255样本，37正/218负，4个sample_at，跨度90天 |
| Sprint 8真实分类训练 | PASS；Logistic/Random Forest/XGBoost均完成Validation/Test |
| Sprint 8 Regression/Learning Curve | PASS；Percentile RF Regression + 25/50/75/100% Curve |
| Sprint 8 Model Registry | PASS；4个VALIDATED，artifact SHA通过，ACTIVE=0 |
| Sprint 9 Backend full test | PASS；127 passed |
| Sprint 9 Ruff / Django check / Migration drift | PASS / 0 issues / No changes detected |
| Sprint 9 PostgreSQL pgvector / real retrieval | PASS；50 Repo、1,501 Chunk、Repository Filter、Evidence |
| Sprint 9 Change Detection | PASS；changed=0、embedding_calls=0、skipped=5 |
| Sprint 10 Backend full test | PASS；134 passed |
| Sprint 10 Ruff / Django check / Migration drift | PASS / 0 issues / No changes detected |
| Sprint 10 Frontend lint/type/test/build | PASS；9 passed；保留既有 bundle size warning |
| Sprint 10 Compose / API smoke | PASS；六服务、两 Migration、PostgreSQL、Redis、Celery、双 Health、Detail/Ranking |
| Sprint 10 real score validation | PASS；39 Repo、12 Category、20 Knowledge-rich + 19 NOT_INGESTED |
| Sprint 11 Backend full test | PASS；139 passed |
| Sprint 11 Ruff / Django check / Migration drift | PASS / 0 issues / No changes detected |
| Sprint 11 MCP stdio / Registry | PASS；13 registered read-only Tools、schema/error/timeout |
| Sprint 11 real Tool calls | PASS；9 calls、PostgreSQL/pgvector、3 Knowledge Evidence、Forecast NOT_READY |
| Sprint 11 Infrastructure | PASS；六服务、双 Health、PostgreSQL、Redis、Celery |
| Sprint 12 Backend full test | PASS；148 passed |
| Sprint 12 Ruff / Django check / Migration drift | PASS / 0 issues / No changes detected |
| Sprint 12 Skill Registry / Dry Run | PASS；6 Skills、6 Intents、Tool reference/read-only validation |
| Sprint 12 real workflows | PASS；6 Workflows、PostgreSQL/pgvector、protected counts unchanged |
| Sprint 12 Infrastructure | PASS；六服务、双 Health、PostgreSQL、Redis、Celery |

## 19. 当前阻塞与下一阶段

Sprint 13 Definition of Done 已满足。单 Agent、Provider abstraction、严格 Intent Router、Entity
Resolver、MCP-only Skill Execution、Evidence Context、Redis Session、Trace、Copilot API 和 Vue UI
均已实现。真实 DeepSeek V4 Pro、真实 PostgreSQL/pgvector/Redis/MCP 六意图 smoke 全部通过；
Forecast 保持 NOT_READY 且没有概率。下一允许 Sprint 为 Sprint 14，本次未进入。

## 20. 更新日志

### 2026-08-16 — Sprint -1

- 完成 GitHub Capability Spike。
- Sprint -1：COMPLETED。

### 2026-08-16 — Sprint 0

- 完成后端、前端、Celery、PostgreSQL/Redis Compose、Lint/Test 与基础文档实现。
- 修复首次前端测试与安装并发造成的工具缺失，以及 ESLint TypeScript 配置加载问题和模板警告。
- 本地全部工程检查通过。
- 因容器运行时缺失无法执行 Compose 运行验收，Sprint 0 真实状态记录为 BLOCKED。
- Sprint 1 保持 NOT_STARTED。

### 2026-08-16 — Sprint 0 容器验收复核

- 只复核 ISSUE-002 与 DEBT-002，未重复已通过的 Sprint 0 工作。
- PATH 和 macOS 常见安装位置均未发现 Docker 或兼容 Runtime。
- `docker compose config --quiet`：退出 127。
- `docker compose up --build -d`：退出 127。
- 无法执行六服务及端到端运行验收。
- Sprint 0 继续为 BLOCKED；DEBT-002 继续 OPEN；Next Allowed Sprint 继续为 Sprint 0。

### 2026-08-16 — Docker Runtime 安装

- Docker Desktop 因 macOS 13 不兼容未安装；采用 Colima 提供 Docker Runtime。
- 安装 Docker CLI、Docker Compose、Colima、Lima、QEMU。
- Colima QEMU VM 启动成功，Docker context 为 `colima`。
- `docker run --rm hello-world`：PASS。
- ISSUE-002 更新为 RESOLVED。
- 随后完成项目 Compose 验收，历史阻塞解除。

### 2026-08-16 — Sprint 0 Compose 运行验收完成

- `docker compose config --quiet` 和 `docker compose up --build -d`：PASS。
- 六服务均持续运行，PostgreSQL 与 Redis healthcheck：healthy。
- Backend Health、Frontend→Backend Health、PostgreSQL、Redis、Celery Worker/Beat：PASS。
- 新增 GitHub Actions Compose smoke job 和 `make compose-smoke`；本地 smoke：PASS。
- DEBT-002：RESOLVED。
- Sprint 0：COMPLETED；Next Allowed Sprint：Sprint 1；Sprint 1 未开始。

### 2026-08-16 — Sprint 1 Repository Domain

- 完成 Repository、Category、Topic 与 Discovery Query Pool 数据模型和 Migration。
- 完成 Real/Fake GitHubClient、Repository Sync、Discovery、规则分类及管理命令。
- 11 个后端测试、Ruff、Django check、Migration drift check：PASS。
- PostgreSQL 容器 Migration、表、种子数据与 Compose 兼容验收：PASS。
- Sprint 1：COMPLETED；Next Allowed Sprint：Sprint 2；Sprint 2 未开始。

### 2026-08-16 — Sprint 2 Snapshot Pipeline

- 完成 Snapshot 模型、6小时 bucket、UPSERT、事务提交钩子和 NULL 语义。
- 完成 Redis TTL Lock、token-safe release、Celery Retry、Task、Beat 与 github_normal 队列。
- 22 个后端测试、Ruff、Django check、Migration drift check：PASS。
- PostgreSQL、Redis、Celery、Compose 真实集成验收：PASS。
- Sprint 2：COMPLETED；Next Allowed Sprint：Sprint 3；Sprint 3 未开始。

### 2026-08-16 — Sprint 3 Activity Intelligence

- 完成 GitHubClient Activity 能力、Activity/Contributor/Release 数据模型和 Migration。
- 完成 Search incomplete→NULL、Contributor Stats 202 Retry、每日 Celery Beat 与双层幂等保护。
- 本地测试/静态检查、公共 GitHub smoke、PostgreSQL/Redis/Celery/Compose 验收：PASS。
- Sprint 3：COMPLETED；Next Allowed Sprint：Sprint 4；未进入 Sprint 4。

### 2026-08-16 — Sprint 4 Trend Engine

- 补齐 Trend 专项文档，完成纯 Python Cohort、Percentile、七组件、Hype 与 Lifecycle。
- 完成版本化 Trend Model、Evidence、UPSERT、提交后 scoring task 和队列。
- 51 项后端测试、全量工程门禁及 PostgreSQL/Redis/Celery/Compose 验收通过。
- Sprint 4：COMPLETED；Next Allowed Sprint：Sprint 5；未进入 Sprint 5。

### 2026-08-16 — Sprint 5 Dashboard

- 完成数据库只读 Dashboard、Discover、Project Detail、Metrics 与 Trend API。
- 完成 Vue Dashboard、Discover、Repository Detail、Snapshot/Activity/Trend 图表及 Score Evidence。
- NULL、完整度、Hype 数据不足与 Sprint 4 algorithm version 在 API/UI 全链路验证通过。
- 58 项后端测试、6 项前端测试、Ruff、ESLint、类型检查、Django check、Migration drift、生产构建和 Compose 验收通过。
- Secret 安全基线更新：仅环境变量读取新 Token，Compose 仅用 `config --quiet` 验证。
- Sprint 5：COMPLETED；Next Allowed Sprint：Sprint 6；未进入 Sprint 6。

### 2026-08-16 — Sprint 6 Potential Engine

- 补齐 Potential V1 专项契约，完成确定性公式、confidence、Hype 缺失降置信度和多信号候选规则。
- 完成版本化 Potential Model/Migration、UPSERT、Trend 后置 Celery task 与 scoring 路由。
- 完成 Potential API、High Potential Ranking、Dashboard/Discover/Detail/Metrics 和中文 Evidence UI。
- 69 项后端、7 项前端测试与全量门禁通过；真实 PostgreSQL Migration/约束、Redis/Celery 双次幂等任务及 API/UI 验收通过。
- 未构建 Historical Dataset、ML、Forecast、RAG、MCP、Skill 或 Agent。
- Sprint 6：COMPLETED；Next Allowed Sprint：Sprint 7；未进入 Sprint 7。

### 2026-08-17 — Sprint 7 Historical Dataset

- 补齐 Dataset/Forecast 边界文档，完成 BACKFILLED Activity Window、Training Sample 与版本化 Migration。
- 完成 Feature V1、Activity Label V1、Category + Age Cohort Percentile、Leakage Guard、UPSERT 与质量报告。
- 真实 GitHub smoke 正确处理 Contributor Stats 202；重试后三窗口、样本幂等和零伪造 Snapshot 验证通过。
- 82 项后端、7 项前端测试与全量门禁、PostgreSQL/Redis/Celery/Compose 验收通过。
- 未训练模型，Forecast 保持 NOT_READY；未进入 Sprint 8。
- Sprint 7：COMPLETED；Next Allowed Sprint：Sprint 8。

### 2026-08-17 — Sprint 8 Machine Learning Forecast

- 完成 Quality Gate、最小 Label Cohort、Time-based Split、三模型训练/评估、Registry、Feature Importance、
  显式激活门禁、Forecast API/UI 与 ml queue 的工程实现和测试。
- 真实 smoke 样本因 cohort=1 被剔除；有效 Dataset=0，训练命令按设计拒绝执行。
- 没有产品模型指标、没有 ACTIVE 模型、没有 Forecast Probability；继续使用 Potential Score。
- Sprint 8：BLOCKED；Next Allowed Sprint：Sprint 8；未进入 Sprint 9。

### 2026-08-17 — Sprint 8 Dataset Acquisition / Sampling

- 完成 836 个真实 Repository 的 Coverage Audit、主要 Category Head Coverage 和有界 Query Sharding。
- 建立 Candidate=836、Tracked=509、分层 Training=300 三层 Pool；Training 已显式 CONFIRMED。
- Head Top 10 初始覆盖 88/100，复用已有记录并补入 12 个，最终 100/100；没有覆盖既有 Repository。
- 没有删除或重置任何业务数据，没有恢复大规模 Backfill，没有训练模型；Sprint 8 继续 BLOCKED。

### 2026-08-17 — Sprint 8 Targeted Dataset / Real Training

- 保持 Candidate 3,081、Training Pool v2 800 CONFIRMED，定向回填 Framework/Multi/Coding。
- 两批后真实 Dataset=255、Positive=37、Negative=218，Quality Gate和Time-based三段门禁通过并Early Stop。
- 完成 Logistic Regression、Random Forest、XGBoost真实Validation/Test及Percentile Regression。
- XGBoost按Validation PR-AUC/F1/Precision优先级胜出；Learning Curve记录MORE_DATA_LIKELY_BENEFICIAL。
- 四个artifact持久化及SHA-256验证通过，Registry均为VALIDATED，ACTIVE=0，Forecast仍NOT_READY。
- 后端全量测试、Ruff、Django check、Migration drift和Compose安全检查通过。
- Sprint 8：COMPLETED；Next Allowed Sprint：Sprint 9；本次停止，未进入Sprint 9。

### 2026-08-17 — Sprint 8.5 Continuous Monitoring

- 修改前只读审计：Snapshot=3,079、覆盖Repository=3,079、平均1.0；≥7天=0、≥30天=0。
- 实现每6小时新项目 Discovery、每日近期 push Refresh；完整复用语义 Query Pool，统一经 GitHubClient。
- 新仓库按 github_id 去重，经 Metadata 和确定性分类后只进入 Candidate、标记 NEW，并在事务提交后创建首条 Snapshot。
- 建立 NEW/HOT/RISING/NORMAL/STABLE/DORMANT/ARCHIVED、集中频率配置和 Repository 调度字段。
- Beat 改为每小时统一 `dispatch_due_snapshots`；按 next time、批量上限与 Core Budget 派发，不创建逐仓库 Beat。
- Snapshot 新增 updated/archive/watcher/origin；保留 Redis Lock、事务、同桶唯一约束和 NULL 语义。
- 有界真实 Discovery 1 Query/2 Results：created=1、reused=1；Candidate v2 从3,081增至3,082，Training未变。
- NEW/NORMAL/STABLE 三仓库 Worker smoke 通过；下次采集分别为+6h/+24h/+72h；同桶重跑不重复。
- 最终 Snapshot=3,084、覆盖Repository=3,080；真实时间跨度仍不足7/30天，所有相应增长保持NULL。
- Repository Holdout：训练62仓库/202样本，Holdout16仓库/53样本、仓库交集0；Precision=1.0、
  Recall=0.916667、F1=0.956522、ROC-AUC=1.0、PR-AUC=1.0。仅作小样本辅助验证，不激活模型。
- 全量后端测试、Ruff、Django check、Migration drift、Compose迁移、PostgreSQL/Redis、Celery Worker/Beat、
  Backend/Frontend Health均PASS。
- ACTIVE Model=0、Forecast rows=0、Forecast=NOT_READY；Sprint 8.5 COMPLETED，本次禁止进入Sprint 9。
- 修复 Dashboard Top Trend 排名：NULL 明确置后，完整度低于50%的项目不参与正式榜单；
  Discover 保留数据不足项目但排序不再将 NULL 放在前面。Trend/Potential 公式及 Sprint 状态未修改。

### 2026-08-17 — Sprint 9 Repository Knowledge RAG Pilot

- 完成版本化 Knowledge Document/Chunk、pgvector、Embedding Provider、Change Detection 与检索。
- 真实 Pilot 停止在50个有效 Repository，未扩到全量3,082 Repository。
- 最终有效数据为302 Document、1,501 Chunk、885,641 approximate tokens。
- Routine batch Search=0；PR/Issue 仅保留真实 Smoke，Structured 数据未进入 RAG。
- 全量后端127项测试、Ruff、Django check、Migration drift 和真实 pgvector/Evidence 验收通过。
- Sprint 9：COMPLETED；Next Allowed Sprint：Sprint 10；本次停止，未进入 Sprint 10。

### 2026-08-17 — Sprint 10 Learning / Enterprise Score

- 完成 `learning-v1.0.0` 与 `enterprise-v1.0.0` 两套确定性、版本化、可解释评分及 Migration。
- 严格区分 NULL/0、`NOT_INGESTED`/`DOCUMENT_NOT_FOUND` 和 `MISSING`/`INSUFFICIENT_HISTORY`。
- 完成 Score Detail API、Discover Filter/Sort/Ranking、可配置 confidence 门禁和中文 Evidence UI。
- 真实评分39个仓库、覆盖12类；指定 Framework/Coding/Browser/Multi/MCP/Research 均覆盖，
  Knowledge-rich=20、NOT_INGESTED=19，Learning eligible=20、Enterprise eligible=15。
- 真实数据库无 archived Repository；归档维护分为真实0的行为由测试覆盖，没有伪造生产数据。
- 后端134项、前端9项测试及 Ruff、Django check、Migration drift、lint、type-check、build 全部通过。
- Compose 六服务、PostgreSQL、Redis、Celery scoring task 注册、Backend/Frontend Health、评分详情与榜单 smoke 通过。
- 保持 Sprint 0～9 数据、Trend/Potential/Forecast/Model Registry 算法与状态不变。
- Sprint 10：COMPLETED；Next Allowed Sprint：Sprint 11；本次停止，未进入 Sprint 11。

### 2026-08-17 — Sprint 11 Internal Tool Layer + MCP

- 建立统一成功/失败 Tool Contract、JSON input/output schema、Registry、版本、只读标记、超时、
  结构化错误、duration/DB query/result bytes metadata。
- 注册13个只读业务 Tool，覆盖 Repository、Trend、Potential、Forecast、Learning、Enterprise、
  Compare、Knowledge Retrieval/Summary 与 Category；没有提前实现 Watchlist。
- MCP Server 采用环境变量配置的 stdio JSON-RPC，仅代理 Registry，不包含 ORM 或算法逻辑。
- 真实子进程完成 initialize、tools/list 与9个必测 tools/call；pgvector 返回3条 Evidence，
  Forecast 明确 NOT_READY，未执行 VALIDATED 模型。
- 真实性能：单项目2～5 queries/约7～45ms，Search 2 queries/86ms，Retrieval 2 queries/14ms；
  Compare 2项目40 queries/147ms，记录为后续 N+1 技术债务。
- 数据保护复核：Repository=3,082、Snapshot=3,084、Activity=1、Trend/Potential=3,081、
  Model=4、Forecast=0、Learning/Enterprise=39、Knowledge Document=328、Chunk=1,544；Tool无写入。
- 后端139项测试、Ruff、Django check、Migration drift，以及六服务、PostgreSQL、Redis、Celery、
  Backend/Frontend Health全部通过；本 Sprint 无数据库 Migration、无前端修改。
- Sprint 11：COMPLETED；Next Allowed Sprint：Sprint 12；本次停止，未进入 Sprint 12。

### 2026-08-17 — Sprint 12 Skill Engine & Workflow Policy

- 新增6份 `skills/*/SKILL.md` 结构化版本化 Policy，覆盖 Trend、Future、Learning、Enterprise、
  Project Analysis 和 Project Comparison，对应6个标准 Intent且一一映射。
- 实现 Skill Contract、Loader、Registry、版本/禁用/未知 Skill、Tool引用与read-only启动校验。
- 实现无执行的 Dry Run，以及无LLM、无自主规划的薄型确定性 Executor、Tool Budget、Stop、Fallback、
  Partial Failure 和脱敏 Execution Trace。
- 真实执行六条 Workflow：Trend因当前历史完整度不足返回INSUFFICIENT_EVIDENCE；Enterprise因
  Maintenance/Knowledge证据不足不强行推荐；Learning、Analysis、Comparison链路成功。
- Future Prediction 首次调用Forecast，真实返回NOT_READY后执行Trend+Potential，结果明确为
  CURRENT_SIGNAL_ANALYSIS，没有概率、没有调用VALIDATED模型。
- 所有真实 Workflow 均通过现有 Tool Registry 查询PostgreSQL/pgvector；执行前后受保护数据行数一致。
- 后端148项测试、Ruff、Django check、Migration drift及六服务、双Health、PostgreSQL、Redis、Celery
  全部通过；本 Sprint 无Migration、无API、无Celery Task、无前端修改。
- 保留Sprint 11 `compare_projects` N+1债务，不在本 Sprint 扩大范围重构。
- Sprint 12：COMPLETED；Next Allowed Sprint：Sprint 13；本次停止，未进入 Sprint 13。

### 2026-08-18 — Sprint 13 PM Copilot Agent

- 建立唯一 PM Copilot Agent：真实 LLM Intent Router → Skill Registry → MCP Client/Server → 现有13个
  只读 Tool → Service/PostgreSQL/pgvector → Evidence → 真实 LLM 中文回答。
- Provider 抽象支持 OpenAI Responses、DeepSeek/OpenAI-compatible Chat Completions；凭据仅从后端环境读取。
- 完成严格 JSON Intent/Answer、各最多一次格式修复、Repository 名称 MCP 解析、Tool Budget、上下文压缩、
  GitHub/RAG Prompt Injection 清洗、NULL/NOT_INGESTED/Forecast 安全规则。
- 完成 Redis TTL Session、脱敏 Trace、`POST /api/v1/copilot/chat` 与中文 Copilot 页面；前端只访问 Backend。
- 固定30题评估集覆盖6个 Intent；真实六意图 smoke 6/6 Intent/Skill 正确，全部 Tool 调用符合白名单和预算，
  深度分析8 calls、比较13 calls、Forecast回退5 calls，未产生 Forecast Probability。
- 后端全量161项测试、Ruff、Django check、Migration drift，前端11项测试、lint、type-check、build 全部通过。
- Compose安全配置、六服务、PostgreSQL/Redis、Celery Worker ready/Beat、Backend/Frontend Health 全部通过。
- 未新增 Migration、未修改评分或模型、未写业务数据、未进入 Sprint 14。
- Sprint 13：COMPLETED；Next Allowed Sprint：Sprint 14。

### 2026-08-18 — Sprint 14 Watchlist / Alert / Scheduled Report

- 新增默认 Watchlist 的添加、幂等重复、取消、列表和 Repository Detail 关注状态；与三类 Pool 隔离。
- 新增8类版本化 Alert Contract 和集中阈值；V1 真实实现 Snapshot增长、Activity、Release、Dormant、
  High Potential，Trend/Potential 当前态无可靠历史时不伪造 change Alert。
- Alert 使用 `(repository, type, rule_version, event_bucket)` 数据库唯一约束；NULL、历史不足、低
  completeness/confidence 均不会触发强提醒。
- 新增 UTC 固定时间桶 Daily/Weekly structured report，事实来自数据库与现有 Evidence，LLM 未参与。
- 新增4个 Celery Task 和 Beat 调度；Snapshot/Activity/Trend/Potential 持久化后派发评估。
- Tool Catalog 13→16，Skill/Intent 6→9；PM Copilot 可只读查询 Watchlist、Alert、Report，无 Agent 写权限。
- 新增中文 Watchlist、Alert、Report 页面、关注按钮、Evidence 和未读状态。
- 真实验收：关注 `octocat/Hello-World` 与 `github/docs`，重复关注未新增，取消后剩1项；真实
  `github_pushed_at` 触发1条 PROJECT_DORMANT，重复 Worker 评估新增0，虚假7d Alert=0；日报、周报均由
  Celery Worker 成功生成并落库，六服务与双 Health 可访问。
- 后端171项 pytest、Ruff、Django check、Migration drift；前端14项 Vitest、lint、type-check、build
  全部通过。Migration `watchlists.0001_initial` 已在真实 PostgreSQL 应用。
- Sprint 14：COMPLETED；Next Allowed Sprint：Sprint 15；本次停止，未进入 Sprint 15。

### 2026-08-18 — Sprint 15 Production Hardening

- 完成正式 Token/Session Authentication；Watchlist、Alert Receipt、Scheduled Report 与 Copilot
  Redis Session 全部绑定 Django User，跨用户 API/Service/Tool 隔离测试通过。旧本地数据迁移到不可登录
  `legacy-local`，没有删除现有数据。
- 增加匿名/用户/Auth/Agent 分层限流、1 MiB 请求限制、安全 Header/Cookie/Proxy 配置、JSON 请求与
  Celery 生命周期日志、request ID；日志不记录 Header、Body 或 Secret。
- 新增 liveness、DB/Redis/config readiness 和 staff-only operations status；GitHub/LLM 不可用显示
  degraded，不伪装核心服务失败。
- Score History 从上线后按6小时真实时间桶幂等记录 Trend/Potential；不回填历史。Trend/Potential
  Change Alert 只有两个真实历史点且完整度达标才触发。
- Compare 2 Repository 从历史约40 queries 降至测试门禁不超过30；Discover 与 Alert 用户查询新增
  复合索引，PostgreSQL EXPLAIN 真实命中 `repo_cat_stars_idx`、`receipt_owner_status_idx`。
- Backend 启动移除隐式 Migration，建立生产 Compose overlay、TLS Nginx 示例、生产环境模板、显式
  发布/回滚流程、CI 全质量门禁、Retention task/命令与 Celery failure/retry 可观测性。
- 真实 PostgreSQL custom dump 恢复至隔离库，9张关键表 count 全部一致；Repository=3,082、
  Snapshot=3,084、Activity=1、Trend/Potential=3,081、Model=4、Knowledge Document=328；验证库已清理。
- 前端新增登录/401状态和私有路由保护；全路由懒加载、ECharts按图表类型拆分，最大 chunk 从约1.26MB
  降到465.72kB，构建无 >500kB 警告。
- 真实 Compose 验收通过 PostgreSQL、Redis PONG、Celery pong、Backend/Frontend readiness；真实 E2E
  通过登录、关注幂等、报告、Alert Celery 和 LLM Copilot Evidence，Token 未输出且 smoke 用户已清理。
- Backend 178项 pytest、Ruff、Django check、Migration drift；Frontend 14项 Vitest、lint、
  type-check、build全部通过。npm生产依赖0漏洞，pip-audit无已知漏洞。
- 轻量性能 smoke：Discover约42ms；Dashboard当前3,082项目冷/热请求仍约7秒，记录为已知性能债务，
  未以缓存掩盖数据真实性。
- Forecast V1、label-v1.2.0、Trend/Potential/Learning/Enterprise算法、Dataset、Model Registry、
  RAG embedding版本保持不变；ACTIVE Model仍为0，Forecast保持NOT_READY。
- Sprint 15：COMPLETED；没有 Sprint 16，未实现 Forecast V2、Multi-Agent 或新业务能力。

### 2026-08-18 — V1 Data Maturity / Capability Auto Activation

- 保持 Sprint 15 COMPLETED；本项为 V1 运维能力增强，不新增业务 Sprint。
- 新增10项统一 Capability 状态、真实覆盖门禁、首次 READY 时间与可审计原因。
- Star/Fork 7d/30d 只接受 OBSERVED Snapshot；NULL 不转 0，BACKFILLED 不参与成熟门禁。
- 新增每日 Celery 评估、Redis 全局锁及每批200仓库的分页重算；首次 READY 才触发既有
  Trend → Potential → Score History → Alert 链路。
- 新增 `category-trend-v1.0.0` 及 Dashboard 自动 fallback；无需未来修改前端代码切换。
- Forecast V2 仅新增 DATA READINESS，未训练、未激活、未替换 Forecast V1。
- 全量 Backend 196项 pytest、Ruff、Django check、Migration drift，以及 Frontend 19项 Vitest、
  lint、type-check、build 全部通过；比较工具查询回归由46降至门禁30以内。
- Migration 已应用至真实 PostgreSQL；Redis PONG、Celery Worker/Beat、Backend/Frontend readiness通过。
  真实评估10项均为 ACCUMULATING（当前3,081个有效Repository尚无7/30天OBSERVED跨度），
  没有伪造READY、没有派发无效重算；Dashboard真实返回 `CATEGORY_DISTRIBUTION` fallback。
- Current Sprint：Sprint 15 COMPLETED；Next Allowed Sprint：无；未进入新业务 Sprint。

### 2026-08-18 — V1 Frontend Workspace Redesign

- 保留登录/注册视觉，重构其余页面的信息层级与响应式排版；没有新增业务 Sprint 或 Backend 能力。
- 智能分析改为独立决策工作台，明确区分分析路径、对话、Evidence、状态元数据和输入区。
- Dashboard 使用编辑式 KPI/排行榜节奏；Discover 使用浮层筛选工作台；Repository Detail 使用研究档案式指标区。
- Watchlist、Alert、Report 使用不同密度和页面色调，避免通过完全相同卡片模板强行统一。
- 主导航补充轻量图形语义；桌面与375px窄屏无横向页面溢出。

### 2026-08-18 — V1 Personal Workspace Layout Refinement

- 保持现有业务与 API 不变，重新设计“我的关注、动态提醒、定期报告”三页的信息架构。
- 我的关注采用研究概览侧栏 + 自适应项目收藏卡；动态提醒采用收件箱筛选 + 事件时间线；
  定期报告采用报告档案导航 + 编辑式报告阅读区，没有机械复制智能分析卡片。
- 保留 Loading、Error、Empty、未读、Evidence、生成日报/周报与取消关注等既有行为。
- Frontend lint、type-check、19项 Vitest、production build 全部通过；本地真实登录页面无控制台错误，
  1,280px 桌面与390px窄屏均无横向溢出。

### 2026-08-18 — PM Copilot Tool Argument Boundary Fix

- 修复 Learning Recommendation 将内部 `user_goal` 透传给 `search_projects`、触发
  `INVALID_ARGUMENT` 的问题。
- Skill Executor 现按目标 Tool 发布的 Input Schema 白名单过滤动态约束；MCP/Tool Registry 仍保留
  `additionalProperties=false` 的最终严格校验，不扩大 Tool 权限或参数范围。
- 新增 Skill Executor 与完整 PM Copilot Runtime 两层回归测试，覆盖中文学习推荐问题和内部上下文隔离。
- 本地真实 `Skill → MCP → Tool → PostgreSQL` 验收返回3个候选、13次合法只读 Tool 调用、
  `COMPLETED` 且 warnings为空；未调用外部 LLM 进行额外数据外发。

### 2026-08-18 — PM Copilot DeepSeek Validated Streaming

- 新增认证 `POST /api/v1/copilot/chat/stream`，通过 SSE 返回工作流状态、答案 delta 与最终完整结果；
  原 JSON `/copilot/chat` 保持兼容。
- DeepSeek/OpenAI-compatible 使用上游 `stream=true`、`include_usage=true`，支持 `: keep-alive`、
  `[DONE]`、增量 content 和末尾 usage；Nginx 对该端点关闭代理缓冲。
- 为保持 Agent 安全边界，Provider 原始 JSON/reasoning 不直通浏览器；答案完整通过 Schema、Evidence、
  NULL 与 Forecast Safety 后才分段展示，最终 Evidence/Trace/Session 一次落定。

### 2026-08-18 — PM Copilot Evidence Presentation Refinement

- 保留原始 Evidence 与可追溯链接，仅优化显示层：结构化 Tool Evidence 按工具来源显示中文语义标题，
  不再重复显示 `STRUCTURED_TOOL_EVIDENCE`。
- README/Docs/Release 等知识证据按 Repository + URL/Path 合并，保留最多3段摘要，清理 Markdown
  围栏、HTML 标签和 Badge 图片噪声，原始文档链接仍可直接打开。
- Evidence 折叠标题分别显示“指标数”和“文档来源数”，避免把 RAG chunk 数误解为独立来源数。

### 2026-08-18 — PM Copilot SSE Content Negotiation Fix

- 修复浏览器使用 `Accept: text/event-stream` 请求 Copilot 流式端点时，DRF 在进入 View 前因缺少
  SSE Renderer 而返回 HTTP 406 的问题。
- 新增 EventStream Renderer 完成内容协商，错误响应仍使用 SSE `error` 事件；不改变认证、限流、
  Evidence 校验或 Agent Runtime 边界。
- API 回归测试现携带与真实浏览器一致的 `Accept: text/event-stream`，防止再次遗漏内容协商问题。

### 2026-08-18 — PM Copilot End-to-End Token Streaming

- 移除“完整生成后每12字定时播放”的伪流式；Tool/Skill/Evidence 先落定，DeepSeek 开始生成后的
  `answer` Provider delta 现通过有界队列和 SSE 实时转发。
- 新增增量 JSON answer 解码器，支持跨 chunk marker、转义字符和 Unicode escape；原始 JSON、reasoning、
  recommendations/warnings token 不暴露。最终 `complete` 仍以完整 Schema 校验结果为准。
- Forecast `CURRENT_SIGNAL_ANALYSIS` 仍先缓冲并通过禁止概率检查，不为获得流式效果降低 Forecast 安全门禁。

### 2026-08-18 — PM Copilot Private Conversation History

- 新增 PostgreSQL 用户私有 Conversation/Message 历史；成功问答自动持久化，未删除会话可恢复问题、
  回答、Evidence 和状态元数据。
- 新增认证分页历史列表、会话详情与删除 API；所有路径按 owner 过滤，跨用户统一404，删除同时
  清理 Redis 短期 Session。
- 智能分析工作台新增历史侧栏、新对话、恢复会话和带不可恢复确认的删除操作。
- Migration 已应用至真实 PostgreSQL；本地真实 API smoke 通过列表200、详情200、跨用户404、删除204且
  剩余行为0。Backend 全量 pytest/Ruff/check/migration drift 与 Frontend 21项 Vitest/lint/type-check/build 通过。

### 2026-08-18 — PM Copilot Streaming Tool Timeout Compatibility

- 修复端到端 Token Streaming 工作线程中 Tool Registry 调用 `signal.SIGALRM`、导致所有真实 Tool
  被脱敏为 `INTERNAL_ERROR` 的线程兼容问题。
- 主线程仍使用预占式 signal timeout；SSE 工作线程改用耗时门禁，Tool Schema、权限、读取范围和
  超时结果语义不变。新增非主线程回归测试。
- 部署后真实 SSE 线程条件下 `MULTI_AGENT + -stars` 搜索0.057秒返回3个项目、`error_code=null`；
  完整 Enterprise Selection 只读 Skill 执行11次 Tool，获得3个 Enterprise Evidence，无 Tool warning。

### 2026-08-18 — PM Copilot Repository Deep Links

- Copilot 响应新增来自 Tool Evidence 的去重 `repository_links`；前端将回答中精确匹配的
  `owner/repository` 渲染为 `/projects/{id}` 站内链接。
- 不使用 `v-html` 或 LLM 产生的 URL。旧历史会话读取时只对 PostgreSQL 中真实存在的项目名补充链接映射。
