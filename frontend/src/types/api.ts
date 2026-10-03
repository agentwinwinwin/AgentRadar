export type NullableNumber = number | null

export interface ProjectSummary {
  id: number
  full_name: string
  description: string | null
  category: string
  primary_language: string | null
  stars: number | null
  forks: number | null
  trend_score: NullableNumber
  data_completeness: NullableNumber
  hype_risk: NullableNumber
  hype_risk_status: string | null
  lifecycle_stage: string | null
  algorithm_version: string | null
  potential_score: NullableNumber
  potential_confidence: NullableNumber
  potential_algorithm_version: string | null
  potential_score_source?: 'DETERMINISTIC_POTENTIAL' | 'STAR_FORECAST_V2'
  deterministic_potential_score?: NullableNumber
  forecast_percentile?: NullableNumber
  forecast_sample_at?: string | null
  learning_score: NullableNumber
  learning_confidence: NullableNumber
  learning_algorithm_version: string | null
  enterprise_score: NullableNumber
  enterprise_confidence: NullableNumber
  enterprise_algorithm_version: string | null
  high_potential: boolean
  potential_candidate: boolean
  breakout_candidate: boolean
  topics: string[]
}

export interface DashboardData {
  statistics: {
    tracked_projects: number
    active_projects: number
    emerging_projects: number
    breakout_projects: number
    high_hype_projects: number
    high_potential_projects: number
    breakout_candidates: number
  }
  top_trend_projects: ProjectSummary[]
  breakout_projects: ProjectSummary[]
  high_hype_projects: ProjectSummary[]
  high_potential_projects: ProjectSummary[]
  high_potential_ranking?: {
    source: 'DETERMINISTIC_POTENTIAL' | 'STAR_FORECAST_V2'
    fallback: 'DETERMINISTIC_POTENTIAL'
    algorithm_version: string
  }
  breakout_candidates: ProjectSummary[]
  lifecycle_distribution: Array<{ stage: string; count: number }>
  category_summary: Array<{
    category: string
    repository_count: number
    average_trend: NullableNumber
  }>
  category_trend: {
    status: 'ACCUMULATING' | 'READY' | 'DEGRADED' | 'DISABLED'
    fallback: 'CATEGORY_DISTRIBUTION' | null
    data_as_of: string | null
    data_coverage: number
    algorithm_version: string | null
    reason: string
    results: Array<{
      category: string
      trend_score: number
      repository_count: number
      eligible_repository_count: number
      data_coverage: number
    }>
  }
}

export interface PaginatedProjects {
  count: number
  next: string | null
  previous: string | null
  results: ProjectSummary[]
}

export interface SnapshotPoint {
  snapshot_at: string
  stars: number | null
  forks: number | null
  subscribers: number | null
  open_issues: number | null
  data_completeness: number
}

export interface ActivityPoint {
  metric_date: string
  commits_7d: number | null
  commits_30d: number | null
  prs_created_7d: number | null
  prs_created_30d: number | null
  prs_merged_7d: number | null
  prs_merged_30d: number | null
  issues_created_7d: number | null
  issues_created_30d: number | null
  issues_closed_7d: number | null
  issues_closed_30d: number | null
  active_contributors_30d: number | null
  releases_30d: number | null
  releases_90d: number | null
  days_since_last_push: number | null
  days_since_last_release: number | null
}

export interface TrendData {
  repository_id: number
  status: 'AVAILABLE' | 'NOT_AVAILABLE'
  trend_score?: number | null
  momentum_score?: number | null
  development_score?: number | null
  community_score?: number | null
  delivery_score?: number | null
  adoption_score?: number | null
  topic_momentum_score?: number | null
  maintenance_score?: number | null
  hype_risk: number | null
  hype_risk_status: string
  lifecycle_stage?: string
  data_completeness: number
  algorithm_version?: string
  calculated_at?: string
  evidence: TrendEvidence | null
}

export interface TrendEvidence {
  calculation_date?: string
  cohort?: { category: string; age: string }
  cohort_size?: number
  missing_inputs?: string[]
  raw_features?: Record<string, number | null>
  percentiles?: Record<string, number | null>
  components?: Record<
    string,
    { score: number | null; completeness: number; inputs: Record<string, number | null> }
  >
}

export interface PotentialEvidence {
  source_trend: { id: number; algorithm_version: string; calculated_at: string }
  inputs: Record<string, number | null>
  weights: Record<string, number>
  component_completeness: Record<string, number>
  base_potential: number | null
  hype_risk: number | null
  hype_risk_status: string
  hype_penalty: number
  missing_inputs: string[]
  candidate_flags: {
    high_potential: boolean
    potential_candidate: boolean
    breakout_candidate: boolean
  }
  candidate_thresholds: Record<string, Record<string, number | boolean>>
}

export interface PotentialData {
  repository_id: number
  status: 'AVAILABLE' | 'NOT_AVAILABLE'
  potential_score: number | null
  confidence: number
  algorithm_version: string
  calculated_at?: string
  evidence: PotentialEvidence | null
  high_potential: boolean
  potential_candidate: boolean
  breakout_candidate: boolean
}

export interface ForecastData {
  repository_id: number
  status: 'READY' | 'PENDING' | 'NOT_READY'
  definition: string
  fallback: 'POTENTIAL_SCORE' | null
  model_version?: string
  reason?: 'INSUFFICIENT_FEATURES'
  forecast: null | {
    model_version: string
    forecast_horizon_days: number
    high_growth_probability: number
    prediction: 0 | 1
    confidence: number
    sample_at: string
    forecast_type?: 'ACTIVITY_FORECAST_V1'
    input_features?: Record<string, string | number | null>
  }
}

export interface DeterministicScoreData {
  repository_id: number
  status: 'AVAILABLE' | 'NOT_AVAILABLE'
  score: number | null
  confidence: number
  algorithm_version: string
  calculated_at?: string
  ranking_eligible: boolean
  recommendation?: 'ADOPT' | 'POC' | 'WATCH' | 'AVOID' | null
  evidence: null | {
    weights: Record<string, number>
    components: Record<string, { value: number | null; status: 'VALUE' | 'MISSING' }>
    knowledge_status: 'INGESTED' | 'NOT_INGESTED' | 'DOCUMENT_NOT_FOUND'
    missing_inputs: string[]
    hype_risk?: number | null
    hype_penalty?: number | null
  }
}

export interface AdminCapabilityData {
  name: string
  status: 'ACCUMULATING' | 'READY' | 'DEGRADED' | 'DISABLED' | 'DATA_READY'
  coverage: number
  first_ready_at: string | null
  last_evaluated_at: string
  reason: string
  algorithm_version: string | null
  metrics: Record<string, unknown>
}

export interface AdminModelData {
  id: number
  model_name: string
  model_version: string
  feature_version: string
  label_version: string
  algorithm: string
  status: 'TRAINED' | 'VALIDATED' | 'ACTIVE' | 'RETIRED'
  training_start: string
  training_end: string
  validation_metrics: Record<string, unknown>
  test_metrics: Record<string, unknown>
  dataset_quality: Record<string, unknown>
  feature_importance: Record<string, unknown>
  artifact_sha256: string
  activation_eligible: boolean
  activation_blockers: string[]
  activated_at: string | null
  prediction_rollout_status: 'NOT_STARTED' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'PARTIAL' | 'FAILED'
  prediction_rollout: Record<string, unknown>
  retraining_targets: Record<string, unknown>
  created_at: string
}

export interface AdminControlCenterData {
  status: 'READY' | 'DEGRADED'
  checked_at: string
  dependencies: Record<string, { status: string; error?: string }>
  product: {
    forecast_status: 'READY' | 'NOT_READY'
    active_model_version: string | null
    validated_model_count: number
    forecast_definition: string
    automatic_activation: false
  }
  capabilities: AdminCapabilityData[]
  models: AdminModelData[]
  training: {
    readiness: AdminTrainingReadiness
    runs: AdminTrainingRun[]
  }
}

export interface AdminTrainingReadiness {
  early_stop: boolean
  quality_gate_passed: boolean
  time_split_ready: boolean
  can_start: boolean
  blocking_run_id: number | null
  feature_version: string
  label_version: string
  confirmation_text: string
  evaluated_at: string
  split_counts: Record<string, { samples: number; positive: number; negative: number }>
  checks: Record<string, { actual: unknown; required: unknown; passed: boolean }>
  quality: Record<string, unknown>
}

export interface AdminTrainingRun {
  id: number
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'BLOCKED'
  feature_version: string
  label_version: string
  celery_task_id: string
  requested_by: string
  requested_at: string
  started_at: string | null
  finished_at: string | null
  dataset_gate_snapshot: Record<string, unknown>
  split_readiness_snapshot: Record<string, unknown>
  result: Record<string, unknown>
  error_code: string | null
  error_message: string | null
}

export interface AdminModelActivationResult {
  model_version: string
  status: 'ACTIVE'
  activated_by: string
}

export interface ProjectDetail extends ProjectSummary {
  owner: string
  name: string
  github_url: string
  description_zh: string
  topics_zh: string[]
  localization_status: 'PENDING' | 'TRANSLATED' | 'FALLBACK'
  homepage: string | null
  subscribers: number | null
  open_issues: number | null
  license_key: string | null
  license_spdx: string | null
  default_branch: string
  is_archived: boolean
  community_health: number | null
  github_created_at: string
  github_updated_at: string
  github_pushed_at: string | null
  last_synced_at: string
  latest_snapshot: SnapshotPoint | null
  latest_activity: ActivityPoint | null
  is_watchlisted: boolean
}

export interface RepositoryComment {
  id: number
  author: { id: number; username: string }
  content: string
  created_at: string
  updated_at: string
}

export interface RepositoryCommunity {
  repository_id: number
  like_count: number
  liked_by_me: boolean
  comment_count: number
  comments: RepositoryComment[]
}

export interface PaginatedRepositoryComments {
  count: number
  next: string | null
  previous: string | null
  results: RepositoryComment[]
}

export interface WatchlistItem {
  repository: ProjectSummary
  added_at: string
}

export interface AlertData {
  id: number
  repository: { id: number; full_name: string }
  alert_type: string
  severity: 'INFO' | 'WARNING' | 'CRITICAL'
  title: string
  evidence: Record<string, unknown>
  detected_at: string
  status: 'UNREAD' | 'READ' | 'DISMISSED'
  rule_version: string
}

export interface ScheduledReportData {
  id: number
  report_type: 'DAILY' | 'WEEKLY'
  period_start: string
  period_end: string
  content: {
    new_repositories: Array<{ id: number; full_name: string; category: string; stars: number | null }>
    watchlist_changes: Array<{ repository: string; action: string; occurred_at: string }>
    alerts: Array<{ id: number; alert_type: string; title: string }>
    insufficient_evidence: Array<{ repository: string; reason: string }>
    facts_source: string
    llm_used: boolean
  }
  rule_version: string
  generated_at: string
}

export interface MetricsData {
  repository_id: number
  range: '7d' | '30d' | '90d'
  snapshots: SnapshotPoint[]
  activity: ActivityPoint[]
  releases: Array<{
    tag_name: string
    name: string | null
    published_at: string | null
    is_prerelease: boolean
  }>
  trend_history: Array<{
    trend_score: number | null
    calculated_at: string
    algorithm_version: string
  }>
  potential_history: Array<{
    potential_score: number | null
    confidence: number
    calculated_at: string
    algorithm_version: string
  }>
}

export interface CopilotEvidence {
  repository?: string
  repository_id?: number
  source_type: string
  title?: string | null
  path?: string | null
  url?: string | null
  snippet?: string
  similarity?: number | null
  updated_at?: string | null
  algorithm_version?: string | null
  confidence?: number | null
  trust?: string
}

export interface CopilotResponse {
  answer: string
  intent: string
  intent_confidence: number
  skill: string
  skill_version: string
  status: string
  recommendations: string[]
  warnings: string[]
  evidence: CopilotEvidence[]
  repository_links?: Array<{ repository_id: number; full_name: string }>
  trace_id: string
  session_id: string
}

export interface CopilotHistorySummary {
  id: number
  session_id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface CopilotHistoryDetail extends CopilotHistorySummary {
  messages: Array<{
    id: number
    role: 'USER' | 'ASSISTANT'
    content: string
    response: CopilotResponse | null
    created_at: string
  }>
}
