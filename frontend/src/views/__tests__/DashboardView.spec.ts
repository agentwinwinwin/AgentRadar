import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import type { ProjectSummary } from '@/types/api'
import DashboardView from '../DashboardView.vue'

vi.mock('@/api/client', () => ({
  api: { dashboard: vi.fn() },
}))

function project(id: number): ProjectSummary {
  return {
    id, full_name: `owner/project-${id}`, description: null, category: 'CODING_AGENT',
    primary_language: 'Python', stars: 100 + id, forks: 10, trend_score: 80 - id,
    data_completeness: 0.8, hype_risk: null, hype_risk_status: 'INSUFFICIENT_HISTORY',
    lifecycle_stage: 'GROWING', algorithm_version: 'trend-v1', potential_score: 70,
    potential_confidence: 0.7, potential_algorithm_version: 'potential-v1',
    learning_score: null, learning_confidence: null, learning_algorithm_version: null,
    enterprise_score: null, enterprise_confidence: null, enterprise_algorithm_version: null,
    high_potential: true, potential_candidate: true, breakout_candidate: false, topics: [],
  }
}

describe('DashboardView', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    vi.mocked(api.dashboard).mockResolvedValue({
      statistics: {
        tracked_projects: 12,
        active_projects: 8,
        emerging_projects: 3,
        breakout_projects: 1,
        high_hype_projects: 0,
        high_potential_projects: 2,
        breakout_candidates: 1,
      },
      top_trend_projects: [],
      breakout_projects: [],
      high_hype_projects: [],
      high_potential_projects: [],
      breakout_candidates: [],
      lifecycle_distribution: [],
      category_summary: [],
      category_trend: {
        status: 'ACCUMULATING',
        fallback: 'CATEGORY_DISTRIBUTION',
        data_as_of: null,
        data_coverage: 0,
        algorithm_version: null,
        reason: '历史积累不足',
        results: [],
      },
    })
  })

  it('loads dashboard data only through the backend client', async () => {
    const wrapper = mount(DashboardView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          EChart: { template: '<div class="chart-stub" />' },
          ProjectTable: { template: '<div class="table-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(api.dashboard).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('人工智能体开源趋势')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('高潜力项目')
    expect(wrapper.text()).toContain('分类项目分布')
    expect(wrapper.text()).not.toContain('Forecast')
    expect(window.localStorage.getItem('agentradar-dashboard-v2')).not.toBeNull()
  })

  it('uses the first result as cache and only reloads after the user refreshes', async () => {
    const cachedData = await vi.mocked(api.dashboard)()
    window.localStorage.setItem(
      'agentradar-dashboard-v2',
      JSON.stringify({ data: cachedData, cachedAt: '2026-08-18T10:30:00.000Z' }),
    )
    vi.clearAllMocks()

    const wrapper = mount(DashboardView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          EChart: { template: '<div class="chart-stub" />' },
          ProjectTable: { template: '<div class="table-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(api.dashboard).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('刷新数据')
    expect(wrapper.text()).toContain('12')

    await wrapper.get('.refresh-button').trigger('click')
    await flushPromises()

    expect(api.dashboard).toHaveBeenCalledOnce()
  })

  it('automatically switches from category distribution to mature category trend', async () => {
    const readyData = await vi.mocked(api.dashboard)()
    readyData.category_trend = {
      status: 'READY',
      fallback: null,
      data_as_of: '2026-08-18T00:00:00Z',
      data_coverage: 0.75,
      algorithm_version: 'category-trend-v1.0.0',
      reason: '门禁通过',
      results: [{
        category: 'CODING_AGENT',
        trend_score: 82,
        repository_count: 30,
        eligible_repository_count: 25,
        data_coverage: 0.83,
      }],
    }
    vi.clearAllMocks()
    vi.mocked(api.dashboard).mockResolvedValue(readyData)

    const wrapper = mount(DashboardView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          EChart: { template: '<div class="chart-stub" />' },
          ProjectTable: { template: '<div class="table-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('分类趋势')
    expect(wrapper.text()).toContain('数据覆盖 75%')
    expect(wrapper.text()).not.toContain('历史成熟后将自动切换')
  })

  it('expands and collapses each ranking independently', async () => {
    const expandedData = await vi.mocked(api.dashboard)()
    expandedData.top_trend_projects = Array.from({ length: 7 }, (_, index) => project(index + 1))
    expandedData.high_potential_projects = Array.from(
      { length: 6 }, (_, index) => project(index + 20),
    )
    vi.mocked(api.dashboard).mockResolvedValue(expandedData)

    const wrapper = mount(DashboardView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          EChart: { template: '<div />' },
          ProjectTable: {
            props: ['projects'],
            template: '<div class="project-count"><span v-if="projects.length === 0">暂无符合条件的项目</span>{{ projects.length }}</div>',
          },
        },
      },
    })
    await flushPromises()

    expect(wrapper.findAll('.project-count').map((item) => item.text())).toEqual(['7', '6'])
    expect(wrapper.text()).not.toContain('暂无符合条件的项目')
    const buttons = wrapper.findAll('.ranking-expand-button')
    expect(buttons[0].text()).toBe('收起全部')
    expect(buttons[1].text()).toBe('收起全部')

    await buttons[0].trigger('click')
    expect(wrapper.findAll('.project-count').map((item) => item.text())).toEqual(['6'])
    expect(buttons[0].text()).toBe('展开全部')
    expect(wrapper.text()).not.toContain('暂无符合条件的项目')

    await buttons[0].trigger('click')
    expect(wrapper.findAll('.project-count').map((item) => item.text())).toEqual(['7', '6'])
    expect(buttons[0].text()).toBe('收起全部')
  })
})
