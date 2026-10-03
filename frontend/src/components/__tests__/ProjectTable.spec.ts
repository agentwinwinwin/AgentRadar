import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import ProjectTable from '@/components/ProjectTable.vue'
import type { ProjectSummary } from '@/types/api'

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/projects/:id', component: { template: '<div />' } }],
})

function project(confidence: number): ProjectSummary {
  return {
    id: 1,
    full_name: 'example/agent',
    description: null,
    category: 'CODING_AGENT',
    primary_language: 'Python',
    stars: 100,
    forks: 10,
    trend_score: 80,
    data_completeness: 0.8,
    hype_risk: null,
    hype_risk_status: 'INSUFFICIENT_HISTORY',
    lifecycle_stage: 'EMERGING',
    potential_score: 99,
    potential_confidence: confidence,
    potential_algorithm_version: 'potential-v1.0.0',
    high_potential: false,
    potential_candidate: false,
    breakout_candidate: false,
  }
}

describe('ProjectTable', () => {
  it('does not present a low-confidence potential score as reliable data', async () => {
    const wrapper = mount(ProjectTable, {
      props: { projects: [project(0.02)] },
      global: { plugins: [router] },
    })

    expect(wrapper.text()).toContain('数据不足')
    expect(wrapper.text()).toContain('置信度 2%')
    expect(wrapper.text()).not.toContain('99.0')
  })

  it('shows followed and unfollowed states in discovery mode', () => {
    const followed = project(0.6)
    const unfollowed = { ...project(0.6), id: 2, full_name: 'example/other-agent' }
    const wrapper = mount(ProjectTable, {
      props: {
        projects: [followed, unfollowed],
        showWatchStatus: true,
        watchedIds: new Set([followed.id]),
      },
      global: { plugins: [router] },
    })

    expect(wrapper.text()).toContain('已关注')
    expect(wrapper.text()).toContain('未关注')
    expect(wrapper.findAll('.watch-status.watched')).toHaveLength(1)
  })
})
