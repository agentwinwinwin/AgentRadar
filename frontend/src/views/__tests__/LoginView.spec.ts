import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import LoginView from '@/views/LoginView.vue'

vi.mock('@/api/client', () => ({ api: { login: vi.fn(), register: vi.fn() } }))
const replace = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace }),
  RouterLink: { template: '<a><slot /></a>' },
}))

describe('LoginView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('switches to registration and creates a new account', async () => {
    vi.mocked(api.register).mockResolvedValue({
      token: 'safe-test-token',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      expires_in: 60,
      user: { id: 1, username: 'new-user', is_staff: false },
    })
    const wrapper = mount(LoginView)
    await wrapper.findAll('.auth-tabs button')[1]?.trigger('click')
    const inputs = wrapper.findAll('input')
    await inputs[0]?.setValue('new-user')
    await inputs[1]?.setValue('A-strong-password-90210')
    await inputs[2]?.setValue('A-strong-password-90210')
    await wrapper.find('form').trigger('submit')
    await vi.waitFor(() => expect(api.register).toHaveBeenCalled())
    expect(window.localStorage.getItem('agentradar_token')).toBe('safe-test-token')
    expect(window.localStorage.getItem('agentradar_user')).toContain('new-user')
    expect(replace).toHaveBeenCalledWith('/dashboard')
  })
})
