import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MetricValue from '../MetricValue.vue'

describe('MetricValue', () => {
  it('distinguishes missing data from a real zero', () => {
    const missing = mount(MetricValue, { props: { value: null } })
    const zero = mount(MetricValue, { props: { value: 0 } })

    expect(missing.text()).toBe('数据不足')
    expect(missing.classes()).toContain('is-missing')
    expect(zero.text()).toBe('0')
    expect(zero.classes()).not.toContain('is-missing')
  })
})

