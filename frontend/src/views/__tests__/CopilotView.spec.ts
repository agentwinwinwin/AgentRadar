import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import CopilotView from '../CopilotView.vue'

vi.mock('@/api/client', () => ({
  api: {
    copilotStream: vi.fn(),
    copilotHistory: vi.fn(),
    copilotHistoryDetail: vi.fn(),
    deleteCopilotHistory: vi.fn(),
  },
}))

describe('CopilotView', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(api.copilotHistory).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    })
    vi.mocked(api.copilotStream).mockImplementation(async (_message, _session, handlers) => {
      handlers.onStatus('正在生成回答…')
      handlers.onDelta('当前证据支持 acme/agent ')
      handlers.onDelta('继续观察。')
      return {
      answer: '当前证据支持 acme/agent 继续观察。',
      intent: 'PROJECT_ANALYSIS',
      intent_confidence: 0.9,
      skill: 'project-analysis',
      skill_version: 'project-analysis-v1.1.0',
      status: 'COMPLETED',
      recommendations: [],
      warnings: [],
      evidence: [
        {
          source_type: 'STRUCTURED_TOOL_EVIDENCE',
          repository_id: 1,
          title: '项目基础信息 · 项目 #1',
        },
        {
          source_type: 'README',
          repository: 'acme/agent',
          title: 'README',
          url: 'https://github.com/acme/agent/blob/main/README.md',
          snippet: '```sh npm install ```',
        },
        {
          source_type: 'README',
          repository: 'acme/agent',
          title: 'README',
          url: 'https://github.com/acme/agent/blob/main/README.md',
          snippet: '<img src="badge.svg"> Core architecture',
        },
      ],
      repository_links: [{ repository_id: 1, full_name: 'acme/agent' }],
      trace_id: 'trace-1',
      session_id: 'session-abcdefghijklmnop',
      }
    })
  })

  it('opens and deletes an owned conversation history', async () => {
    vi.mocked(api.copilotHistory).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{
        id: 9,
        session_id: 'history-session-abcdefghijklmnop',
        title: '分析历史项目',
        message_count: 2,
        created_at: '2026-08-18T00:00:00Z',
        updated_at: '2026-08-18T00:01:00Z',
      }],
    })
    vi.mocked(api.copilotHistoryDetail).mockResolvedValue({
      id: 9,
      session_id: 'history-session-abcdefghijklmnop',
      title: '分析历史项目',
      message_count: 2,
      created_at: '2026-08-18T00:00:00Z',
      updated_at: '2026-08-18T00:01:00Z',
      messages: [
        { id: 1, role: 'USER', content: '历史问题', response: null, created_at: '2026-08-18T00:00:00Z' },
        { id: 2, role: 'ASSISTANT', content: '历史回答', response: null, created_at: '2026-08-18T00:01:00Z' },
      ],
    })
    vi.mocked(api.deleteCopilotHistory).mockResolvedValue(undefined)
    const wrapper = mount(CopilotView, {
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('分析历史项目')

    await wrapper.get('.history-open').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('历史问题')
    expect(wrapper.text()).toContain('历史回答')

    await wrapper.get('.history-delete').trigger('click')
    await flushPromises()
    expect(api.deleteCopilotHistory).toHaveBeenCalledWith(9)
  })

  it('submits a question and renders answer evidence', async () => {
    const wrapper = mount(CopilotView, {
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })
    await wrapper.get('textarea').setValue('分析项目')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.copilotStream).toHaveBeenCalledWith(
      '分析项目',
      undefined,
      expect.objectContaining({ onStatus: expect.any(Function), onDelta: expect.any(Function) }),
    )
    expect(wrapper.text()).toContain('当前证据支持 acme/agent 继续观察')
    expect(wrapper.get('.answer-project-link').attributes('href')).toBe('/projects/1')
    expect(wrapper.text()).toContain('查看证据（1 项指标 · 1 个文档来源）')
    expect(wrapper.text()).toContain('结构化指标')
    expect(wrapper.findAll('.document-evidence-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('npm install')
    expect(wrapper.text()).not.toContain('```')
    expect(window.localStorage.getItem('agentradar-copilot-session')).toBe(
      'session-abcdefghijklmnop',
    )
  })
})
