const categoryLabels: Record<string, string> = {
  AGENT_FRAMEWORK: '智能体框架',
  CODING_AGENT: '编程智能体',
  BROWSER_AGENT: '浏览器智能体',
  RESEARCH_AGENT: '研究智能体',
  MULTI_AGENT: '多智能体',
  AGENT_MEMORY: '智能体记忆',
  AGENT_WORKFLOW: '智能体工作流',
  MCP_TOOL: '模型上下文协议工具',
  COMPUTER_USE: '计算机操作',
  AGENT_OBSERVABILITY: '智能体可观测性',
  AGENT_SECURITY: '智能体安全',
  OTHER_AGENT: '其他智能体',
}

const lifecycleLabels: Record<string, string> = {
  EMERGING: '新兴',
  ACCELERATING: '加速增长',
  BREAKOUT: '突破',
  GROWING: '稳步增长',
  MATURE: '成熟',
  COOLING: '热度回落',
  DORMANT: '休眠',
}

const hypeLabels: Record<string, string> = {
  LOW: '低风险',
  MEDIUM: '中等风险',
  HIGH: '高风险',
  INSUFFICIENT_HISTORY: '历史数据不足',
}

const ageLabels: Record<string, string> = {
  AGE_0_30: '创建 0～30 天',
  AGE_31_180: '创建 31～180 天',
  AGE_181_730: '创建 181～730 天',
  AGE_731_PLUS: '创建超过 730 天',
}

const evidenceLabels: Record<string, string> = {
  momentum: '增长动量',
  development: '开发活跃度',
  community: '社区活跃度',
  delivery: '交付能力',
  adoption: '采用情况',
  topic_momentum: '主题热度',
  maintenance: '维护状态',
  star_growth_30d: '30 日星标增长',
  stars: '星标数',
  forks: '复刻数',
  star_delta_7d: '7 日星标增量',
  star_growth_7d: '7 日星标增长率',
  fork_delta_7d: '7 日复刻增量',
  star_delta_30d: '30 日星标增量',
  fork_delta_30d: '30 日复刻增量',
  star_acceleration: '星标增长加速度',
  commits_30d: '30 日代码提交',
  prs_created_30d: '30 日新建合并请求',
  prs_merged_30d: '30 日已合并请求',
  active_contributors_30d: '30 日活跃贡献者',
  issues_created_30d: '30 日新建议题',
  issues_closed_30d: '30 日关闭议题',
  releases_30d: '30 日发布次数',
  releases_90d: '90 日发布次数',
  days_since_last_push: '距最近代码推送天数',
  days_since_last_release: '距最近发布天数',
  community_health: '社区健康度',
  contributor_diversity: '贡献者多样性',
  topic_momentum_score: '主题热度评分',
}

function label(mapping: Record<string, string>, value: string | null | undefined): string {
  if (!value) return '数据不足'
  return mapping[value] ?? value
}

export const categoryLabel = (value: string | null | undefined) => label(categoryLabels, value)
export const lifecycleLabel = (value: string | null | undefined) => label(lifecycleLabels, value)
export const hypeLabel = (value: string | null | undefined) => label(hypeLabels, value)
export const ageLabel = (value: string | null | undefined) => label(ageLabels, value)
export const evidenceLabel = (value: string) => evidenceLabels[value] ?? value
