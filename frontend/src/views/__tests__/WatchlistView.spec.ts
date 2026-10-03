import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import WatchlistView from '../WatchlistView.vue'

vi.mock('@/api/client', () => ({ api: { watchlist: vi.fn(), unwatch: vi.fn() } }))

describe('WatchlistView', () => {
  it('renders persisted watchlist projects', async () => {
    vi.mocked(api.watchlist).mockResolvedValue({
      results: [{ repository: { id: 1, full_name: 'acme/agent', category: 'CODING_AGENT', trend_score: 80, potential_score: 75 } as never, added_at: '2026-08-18' }],
    })
    const wrapper = mount(WatchlistView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    expect(wrapper.text()).toContain('acme/agent')
    expect(wrapper.text()).toContain('取消关注')
  })
})
