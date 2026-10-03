import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PotentialEvidence from '../PotentialEvidence.vue'

describe('PotentialEvidence', () => {
  it('explains confidence, missing hype and candidate status without forecast wording', () => {
    const wrapper = mount(PotentialEvidence, {
      props: {
        potential: {
          repository_id: 1,
          status: 'AVAILABLE',
          potential_score: 78,
          confidence: 0.55,
          algorithm_version: 'potential-v1.0.0',
          high_potential: true,
          potential_candidate: true,
          breakout_candidate: false,
          evidence: {
            source_trend: { id: 2, algorithm_version: 'trend-v1.0.0', calculated_at: '2026-08-16T00:00:00Z' },
            inputs: { trend: 80, topic_momentum: null, novelty: null },
            weights: { trend: 0.25, topic_momentum: 0.2, novelty: 0.1 },
            component_completeness: { trend: 0.8, topic_momentum: 0, novelty: 0 },
            base_potential: 78,
            hype_risk: null,
            hype_risk_status: 'INSUFFICIENT_HISTORY',
            hype_penalty: 0,
            missing_inputs: ['topic_momentum', 'novelty', 'hype_risk'],
            candidate_flags: { high_potential: true, potential_candidate: true, breakout_candidate: false },
            candidate_thresholds: {},
          },
        },
      },
    })

    expect(wrapper.text()).toContain('当前多信号潜力评分说明')
    expect(wrapper.text()).toContain('置信度：55%')
    expect(wrapper.text()).toContain('历史数据不足')
    expect(wrapper.text()).toContain('高潜力项目')
    expect(wrapper.text()).not.toContain('上涨概率')
    expect(wrapper.text()).not.toContain('Forecast')
  })
})
