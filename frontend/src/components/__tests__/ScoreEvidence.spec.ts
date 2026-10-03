import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ScoreEvidence from '../ScoreEvidence.vue'

describe('ScoreEvidence', () => {
  it('shows algorithm, completeness and missing evidence', () => {
    const wrapper = mount(ScoreEvidence, {
      props: {
        trend: {
          repository_id: 1,
          status: 'AVAILABLE',
          hype_risk: null,
          hype_risk_status: 'INSUFFICIENT_HISTORY',
          data_completeness: 0.7,
          algorithm_version: 'trend-v1.0.0',
          evidence: {
            cohort: { category: 'BROWSER_AGENT', age: 'AGE_31_180' },
            cohort_size: 4,
            missing_inputs: ['star_growth_30d'],
            components: {
              momentum: { score: null, completeness: 0.2, inputs: {} },
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('trend-v1.0.0')
    expect(wrapper.text()).toContain('数据不足')
    expect(wrapper.text()).toContain('整体完整度：70%')
    expect(wrapper.text()).toContain('30 日星标增长')
  })
})
