import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import RepositoryDetailView from '../RepositoryDetailView.vue'

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '7' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/api/client', () => ({
  api: {
    project: vi.fn(),
    trend: vi.fn(),
    potential: vi.fn(),
    forecast: vi.fn(),
    learning: vi.fn(),
    enterprise: vi.fn(),
    metrics: vi.fn(),
    community: vi.fn(),
    like: vi.fn(),
    unlike: vi.fn(),
    comment: vi.fn(),
  },
}))

describe('RepositoryDetailView', () => {
  beforeEach(() => {
    vi.mocked(api.project).mockResolvedValue({
      id: 7,
      full_name: 'agent/example',
      description: null,
      category: 'BROWSER_AGENT',
      primary_language: 'Python',
      stars: null,
      forks: 0,
      trend_score: 71,
      data_completeness: 0.6,
      hype_risk: null,
      hype_risk_status: 'INSUFFICIENT_HISTORY',
      lifecycle_stage: 'EMERGING',
      algorithm_version: 'trend-v1.0.0',
      potential_score: null,
      potential_confidence: null,
      potential_algorithm_version: null,
      high_potential: false,
      potential_candidate: false,
      breakout_candidate: false,
      topics: [],
      owner: 'agent',
      name: 'example',
      github_url: 'https://github.com/agent/example',
      description_zh: '用于浏览器自动化的智能体项目。',
      topics_zh: ['浏览器自动化'],
      localization_status: 'TRANSLATED',
      homepage: null,
      subscribers: null,
      open_issues: null,
      license_key: null,
      license_spdx: null,
      default_branch: 'main',
      is_archived: false,
      community_health: null,
      github_created_at: '2026-01-01T00:00:00Z',
      github_updated_at: '2026-08-16T00:00:00Z',
      github_pushed_at: null,
      last_synced_at: '2026-08-16T00:00:00Z',
      latest_snapshot: null,
      latest_activity: null,
      is_watchlisted: false,
    })
    vi.mocked(api.trend).mockResolvedValue({
      repository_id: 7,
      status: 'AVAILABLE',
      trend_score: 71,
      hype_risk: null,
      hype_risk_status: 'INSUFFICIENT_HISTORY',
      data_completeness: 0.6,
      algorithm_version: 'trend-v1.0.0',
      evidence: { missing_inputs: ['star_growth_30d'] },
    })
    vi.mocked(api.potential).mockResolvedValue({
      repository_id: 7,
      status: 'NOT_AVAILABLE',
      potential_score: null,
      confidence: 0,
      algorithm_version: 'potential-v1.0.0',
      evidence: null,
      high_potential: false,
      potential_candidate: false,
      breakout_candidate: false,
    })
    vi.mocked(api.forecast).mockResolvedValue({
      repository_id: 7,
      status: 'NOT_READY',
      definition: '未来30天进入同 Category 高开发活跃增长组的概率',
      fallback: 'POTENTIAL_SCORE',
      forecast: null,
    })
    const unavailableScore = {
      repository_id: 7,
      status: 'NOT_AVAILABLE' as const,
      score: null,
      confidence: 0,
      algorithm_version: 'score-v1.0.0',
      ranking_eligible: false,
      evidence: null,
    }
    vi.mocked(api.learning).mockResolvedValue(unavailableScore)
    vi.mocked(api.enterprise).mockResolvedValue(unavailableScore)
    vi.mocked(api.metrics).mockResolvedValue({
      repository_id: 7,
      range: '30d',
      snapshots: [],
      activity: [],
      releases: [],
      trend_history: [],
      potential_history: [],
    })
    vi.mocked(api.community).mockResolvedValue({
      repository_id: 7,
      like_count: 2,
      liked_by_me: false,
      comment_count: 1,
      comments: [{
        id: 1,
        author: { id: 3, username: 'reviewer' },
        content: '值得持续关注',
        created_at: '2026-08-18T00:00:00Z',
        updated_at: '2026-08-18T00:00:00Z',
      }],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows null metrics and insufficient hype without fabricating zero', async () => {
    const wrapper = mount(RepositoryDetailView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          EChart: { template: '<div class="chart-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('返回发现项目')
    expect(wrapper.text()).not.toContain('潜力评分记录')

    expect(api.project).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('agent/example')
    expect(wrapper.text()).toContain('用于浏览器自动化的智能体项目')
    expect(wrapper.text()).toContain('浏览器自动化')
    expect(wrapper.text()).toContain('数据不足')
    expect(wrapper.text()).toContain('历史数据不足')
    expect(wrapper.text()).toContain('尚无潜力评分数据')
    expect(wrapper.text()).toContain('模型尚未达到生产启用条件')
    expect(wrapper.get('.github-button').attributes('href')).toBe('https://github.com/agent/example')
    expect(wrapper.text()).toContain('点赞 · 2')
    expect(wrapper.text()).toContain('值得持续关注')
  })

  it('shows original content immediately and refreshes after background localization', async () => {
    vi.useFakeTimers()
    const translated = await api.project(7)
    vi.mocked(api.project).mockClear()
    vi.mocked(api.project)
      .mockResolvedValueOnce({
        ...translated,
        description_zh: 'Original English description.',
        topics_zh: ['agent-tool'],
        localization_status: 'PENDING',
      })
      .mockResolvedValueOnce({
        ...translated,
        description_zh: '中文项目简介。',
        topics_zh: ['智能体工具'],
        localization_status: 'TRANSLATED',
      })

    const wrapper = mount(RepositoryDetailView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          EChart: { template: '<div class="chart-stub" />' },
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('Original English description.')
    expect(wrapper.text()).toContain('正在后台生成中文翻译')

    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(wrapper.text()).toContain('中文项目简介。')
    expect(wrapper.text()).not.toContain('正在后台生成中文翻译')
    expect(api.project).toHaveBeenCalledTimes(2)
  })

  it('renders the active binary forecast card before repository charts', async () => {
    vi.mocked(api.forecast).mockResolvedValue({
      repository_id: 7,
      status: 'READY',
      definition: '未来30天进入同 Category 高开发活跃增长组的概率',
      fallback: null,
      forecast: {
        model_version: 'forecast-v1-active',
        forecast_horizon_days: 30,
        high_growth_probability: 0.73,
        prediction: 1,
        confidence: 0.46,
        sample_at: '2026-08-18T00:00:00Z',
        forecast_type: 'ACTIVITY_FORECAST_V1',
        input_features: { current_stars: 1200, commit_30d: 42 },
      },
    })
    const wrapper = mount(RepositoryDetailView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          EChart: { template: '<div class="chart-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('73%')
    expect(wrapper.text()).toContain('二分类模型')
    expect(wrapper.text()).toContain('近 30 天提交')
    expect(wrapper.text()).toContain('42')
    expect(wrapper.text().indexOf('未来活跃增长预测')).toBeLessThan(
      wrapper.text().indexOf('星标与复刻快照'),
    )
  })
})
