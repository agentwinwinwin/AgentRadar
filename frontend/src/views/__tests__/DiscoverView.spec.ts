import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import DiscoverView from '../DiscoverView.vue'

vi.mock('@/api/client', () => ({
  api: { projects: vi.fn(), watchlist: vi.fn() },
}))

describe('DiscoverView', () => {
  beforeEach(() => {
    vi.mocked(api.projects).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
  })

  it('loads paginated projects from the backend', async () => {
    const wrapper = mount(DiscoverView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          ProjectTable: { template: '<div class="table-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(api.projects).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('发现智能体项目')
    expect(wrapper.text()).toContain('0 个项目')
  })
})
