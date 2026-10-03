import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import AlertsView from '../AlertsView.vue'

vi.mock('@/api/client', () => ({ api: { alerts: vi.fn(), updateAlert: vi.fn() } }))

describe('AlertsView', () => {
  it('shows rule evidence and unread status', async () => {
    vi.mocked(api.alerts).mockResolvedValue({ results: [{ id: 1, repository: { id: 1, full_name: 'acme/agent' }, alert_type: 'NEW_RELEASE', severity: 'INFO', title: '发布新版本', evidence: { tag_name: 'v1' }, detected_at: '2026-08-18T00:00:00Z', status: 'UNREAD', rule_version: 'alerts-v1.0.0' }] })
    const wrapper = mount(AlertsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    expect(wrapper.text()).toContain('发布新版本')
    expect(wrapper.text()).toContain('未读')
    expect(wrapper.text()).toContain('查看证据')
  })
})
