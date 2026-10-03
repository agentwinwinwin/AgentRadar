import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DeterministicScoreEvidence from '@/components/DeterministicScoreEvidence.vue'

describe('DeterministicScoreEvidence', () => {
  it('shows low confidence and not-ingested knowledge without turning it into zero', () => {
    const wrapper = mount(DeterministicScoreEvidence, {
      props: {
        title: '学习价值',
        score: {
          repository_id: 1,
          status: 'AVAILABLE',
          score: 70,
          confidence: 0.2,
          algorithm_version: 'learning-v1.0.0',
          ranking_eligible: false,
          evidence: {
            weights: { documentation: 20 },
            components: { documentation: { value: null, status: 'MISSING' } },
            knowledge_status: 'NOT_INGESTED',
            missing_inputs: ['documentation'],
          },
        },
      },
    })
    expect(wrapper.text()).toContain('数据积累中 / 数据不足')
    expect(wrapper.text()).toContain('知识文档尚未采集')
    expect(wrapper.text()).toContain('数据缺失')
  })
})
