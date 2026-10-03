import type {
  DashboardData,
  DeterministicScoreData,
  ForecastData,
  MetricsData,
  PaginatedProjects,
  PotentialData,
  ProjectDetail,
  TrendData,
  CopilotResponse,
  CopilotHistoryDetail,
  CopilotHistorySummary,
  WatchlistItem,
  AlertData,
  ScheduledReportData,
  RepositoryComment,
  RepositoryCommunity,
  PaginatedRepositoryComments,
  AdminControlCenterData,
  AdminTrainingReadiness,
  AdminTrainingRun,
  AdminModelActivationResult,
} from '@/types/api'
import type { AuthUser } from '@/auth/session'
import { clearAuthSession, getAuthToken } from '@/auth/session'

interface AuthResponse {
  token: string
  expires_at: string
  expires_in: number
  user: AuthUser
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAuthToken()
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null
    if (response.status === 401) {
      clearAuthSession()
      throw new Error('登录状态已失效，请重新登录')
    }
    const fieldError = payload
      ? Object.values(payload).flatMap((value) =>
          Array.isArray(value) ? value : typeof value === 'string' ? [value] : [],
        )[0]
      : undefined
    throw new Error(
      (typeof payload?.message === 'string' ? payload.message : undefined) ??
        (typeof payload?.detail === 'string' ? payload.detail : undefined) ??
        fieldError ??
        (response.status === 404 ? '请求的数据不存在' : `请求失败（${response.status}）`),
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

interface CopilotStreamHandlers {
  onStatus: (message: string) => void
  onDelta: (text: string) => void
}

async function copilotStream(
  message: string,
  sessionId: string | undefined,
  handlers: CopilotStreamHandlers,
): Promise<CopilotResponse> {
  const token = getAuthToken()
  const response = await fetch('/api/v1/copilot/chat/stream', {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Token ${token}` } : {}),
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  if (response.status === 401) {
    clearAuthSession()
    throw new Error('登录状态已失效，请重新登录')
  }
  if (!response.ok || !response.body) throw new Error(`流式请求失败（${response.status}）`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed: CopilotResponse | undefined
  let streamError: string | undefined

  const consume = (block: string) => {
    const lines = block.split(/\r?\n/)
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
    const rawData = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n')
    if (!event || !rawData) return
    const data = JSON.parse(rawData) as Record<string, unknown>
    if (event === 'status' && typeof data.message === 'string') handlers.onStatus(data.message)
    if (event === 'delta' && typeof data.text === 'string') handlers.onDelta(data.text)
    if (event === 'complete') completed = data as unknown as CopilotResponse
    if (event === 'error') streamError = typeof data.message === 'string' ? data.message : '智能分析暂时不可用'
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(consume)
    if (done) break
  }
  if (buffer.trim()) consume(buffer)
  if (streamError) throw new Error(streamError)
  if (!completed) throw new Error('流式回答未完整结束')
  return completed
}

export const api = {
  login: (username: string, password: string) =>
    request<AuthResponse>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  register: (username: string, password: string, passwordConfirm: string) =>
    request<AuthResponse>('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, password_confirm: passwordConfirm }),
    }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<AuthUser>('/auth/me'),
  adminControlCenter: () => request<AdminControlCenterData>('/operations/control-center'),
  checkAdminTraining: () => request<AdminTrainingReadiness>('/operations/training/check', { method: 'POST' }),
  startAdminTraining: (confirmation: string) => request<AdminTrainingRun>('/operations/training/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmation }),
  }),
  adminTrainingRun: (runId: number) => request<AdminTrainingRun>(`/operations/training/runs/${runId}`),
  activateAdminModel: (modelVersion: string, confirmation: string) =>
    request<AdminModelActivationResult>(
      `/operations/models/${encodeURIComponent(modelVersion)}/activate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation }),
      },
    ),
  dashboard: () => request<DashboardData>('/dashboard'),
  projects: (params: URLSearchParams) => request<PaginatedProjects>(`/projects?${params}`),
  project: (id: number) => request<ProjectDetail>(`/projects/${id}`),
  community: (id: number) => request<RepositoryCommunity>(`/projects/${id}/community`),
  like: (id: number) => request<RepositoryCommunity>(`/projects/${id}/like`, { method: 'POST' }),
  unlike: (id: number) => request<void>(`/projects/${id}/like`, { method: 'DELETE' }),
  comment: (id: number, content: string) =>
    request<RepositoryComment>(`/projects/${id}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }),
  comments: (id: number, page = 1) =>
    request<PaginatedRepositoryComments>(`/projects/${id}/comments?page=${page}`),
  metrics: (id: number, range: '7d' | '30d' | '90d') =>
    request<MetricsData>(`/projects/${id}/metrics?range=${range}`),
  trend: (id: number) => request<TrendData>(`/projects/${id}/trend`),
  potential: (id: number) => request<PotentialData>(`/projects/${id}/potential`),
  forecast: (id: number) => request<ForecastData>(`/projects/${id}/forecast`),
  learning: (id: number) => request<DeterministicScoreData>(`/projects/${id}/learning`),
  enterprise: (id: number) => request<DeterministicScoreData>(`/projects/${id}/enterprise`),
  copilot: (message: string, sessionId?: string) =>
    request<CopilotResponse>('/copilot/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    }),
  copilotStream,
  copilotHistory: () =>
    request<{ count: number; next: string | null; previous: string | null; results: CopilotHistorySummary[] }>(
      '/copilot/history',
    ),
  copilotHistoryDetail: (id: number) => request<CopilotHistoryDetail>(`/copilot/history/${id}`),
  deleteCopilotHistory: (id: number) =>
    request<void>(`/copilot/history/${id}`, { method: 'DELETE' }),
  watchlist: () => request<{ results: WatchlistItem[] }>('/watchlist'),
  watch: (repositoryId: number) =>
    request<WatchlistItem>('/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repository_id: repositoryId }),
    }),
  unwatch: (repositoryId: number) =>
    request<void>(`/watchlist/${repositoryId}`, { method: 'DELETE' }),
  alerts: (params = new URLSearchParams()) =>
    request<{ results: AlertData[] }>(`/alerts${params.size ? `?${params}` : ''}`),
  updateAlert: (id: number, status: 'READ' | 'DISMISSED') =>
    request<AlertData>(`/alerts/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }),
  reports: (reportType?: 'DAILY' | 'WEEKLY') =>
    request<{ results: ScheduledReportData[] }>(
      `/reports${reportType ? `?report_type=${reportType}` : ''}`,
    ),
  generateReport: (reportType: 'DAILY' | 'WEEKLY') =>
    request<ScheduledReportData>('/reports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: reportType }),
    }),
}
