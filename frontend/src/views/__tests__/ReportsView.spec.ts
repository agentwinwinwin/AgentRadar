import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import ReportsView from '../ReportsView.vue'

vi.mock('@/api/client', () => ({ api: { reports: vi.fn(), generateReport: vi.fn() } }))

describe('ReportsView', () => {
  it('shows structured report counts and provenance', async () => {
    vi.mocked(api.reports).mockResolvedValue({ results: [{ id: 1, report_type: 'DAILY', period_start: '2026-08-17T00:00:00Z', period_end: '2026-08-18T00:00:00Z', content: { new_repositories: [], watchlist_changes: [], alerts: [], insufficient_evidence: [{ repository: 'acme/agent', reason: '7D_SNAPSHOT_HISTORY' }], facts_source: 'STRUCTURED_DATABASE_AND_EXISTING_EVIDENCE', llm_used: false }, rule_version: 'reports-v1.0.0', generated_at: '2026-08-18T00:00:00Z' }] })
    const wrapper = mount(ReportsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    expect(wrapper.text()).toContain('证据不足项')
    expect(wrapper.text()).toContain('未使用 LLM 计算')
  })
})
