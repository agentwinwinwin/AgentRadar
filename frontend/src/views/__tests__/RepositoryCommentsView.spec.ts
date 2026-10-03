import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import RepositoryCommentsView from '../RepositoryCommentsView.vue'

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '7' }, fullPath: '/projects/7/comments' }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/api/client', () => ({
  api: {
    project: vi.fn(),
    community: vi.fn(),
    comments: vi.fn(),
    comment: vi.fn(),
  },
}))

describe('RepositoryCommentsView', () => {
  beforeEach(() => {
    vi.mocked(api.project).mockResolvedValue({ id: 7, full_name: 'agent/example' } as never)
    vi.mocked(api.community).mockResolvedValue({
      repository_id: 7,
      like_count: 4,
      liked_by_me: false,
      comment_count: 2,
      comments: [],
    })
    vi.mocked(api.comments).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [
        { id: 2, author: { id: 4, username: 'second' }, content: '第二个观点', created_at: '2026-08-18T01:00:00Z', updated_at: '2026-08-18T01:00:00Z' },
        { id: 1, author: { id: 3, username: 'first' }, content: '第一个观点', created_at: '2026-08-18T00:00:00Z', updated_at: '2026-08-18T00:00:00Z' },
      ],
    })
  })

  it('shows public comments from different users on a dedicated page', async () => {
    const wrapper = mount(RepositoryCommentsView, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(api.comments).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('agent/example')
    expect(wrapper.text()).toContain('2 条评论')
    expect(wrapper.text()).toContain('first')
    expect(wrapper.text()).toContain('第一个观点')
    expect(wrapper.text()).toContain('second')
    expect(wrapper.text()).toContain('第二个观点')
  })
})
