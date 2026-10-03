import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { clearAuthSession, setAuthSession } from '@/auth/session'
import AppShell from '../AppShell.vue'

const push = vi.fn()
const routeState = vi.hoisted(() => ({ path: '/dashboard' }))

vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
  useRouter: () => ({ push, currentRoute: { value: routeState } }),
}))

vi.mock('@/api/client', () => ({ api: { logout: vi.fn() } }))

describe('AppShell authentication navigation', () => {
  beforeEach(() => {
    clearAuthSession()
    routeState.path = '/dashboard'
    vi.clearAllMocks()
    vi.mocked(api.logout).mockResolvedValue(undefined)
  })

  it('hides personal features and shows login for guests', () => {
    const wrapper = mount(AppShell)

    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).not.toContain('我的关注')
    expect(wrapper.text()).not.toContain('智能分析')
  })

  it('shows the user and clears the session on logout', async () => {
    setAuthSession(
      'test-token',
      { id: 1, username: 'alice', is_staff: false },
      new Date(Date.now() + 60_000).toISOString(),
    )
    const wrapper = mount(AppShell)

    expect(wrapper.text()).toContain('alice')
    expect(wrapper.text()).toContain('我的关注')
    expect(wrapper.text()).not.toContain('登录')

    await wrapper.get('.account-button').trigger('click')
    await flushPromises()

    expect(api.logout).toHaveBeenCalledOnce()
    expect(window.localStorage.getItem('agentradar_token')).toBeNull()
    expect(push).toHaveBeenCalledWith('/login')
  })

  it('only shows the control center to staff users', () => {
    setAuthSession(
      'test-token',
      { id: 2, username: 'operator', is_staff: true },
      new Date(Date.now() + 60_000).toISOString(),
    )
    const wrapper = mount(AppShell)

    expect(wrapper.text()).toContain('管理控制台')
  })

  it('keeps discover navigation active on project detail routes', () => {
    routeState.path = '/projects/7'
    const wrapper = mount(AppShell)
    const discoverLink = wrapper.findAll('a').find((link) => link.text().includes('发现项目'))

    expect(discoverLink?.classes()).toContain('router-link-active')
  })
})
