import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../client'

describe('backend API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the backend origin and never calls GitHub', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ count: 0, next: null, previous: null, results: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.projects(new URLSearchParams({ q: 'agent' }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/projects?q=agent',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
    expect(fetchMock.mock.calls[0]?.[0]).not.toContain('github.com')
  })

  it('posts Copilot questions only to the backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ answer: '回答', session_id: 'session-abcdefghijklmnop' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.copilot('分析项目', 'session-abcdefghijklmnop')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/copilot/chat',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock.mock.calls[0]?.[1]?.body).not.toContain('API_KEY')
  })

  it('parses Copilot SSE status, deltas and the final validated result', async () => {
    const encoder = new TextEncoder()
    const complete = {
      answer: '流式回答',
      session_id: 'session-abcdefghijklmnop',
      intent: 'PROJECT_ANALYSIS',
      intent_confidence: 0.9,
      skill: 'project-analysis',
      skill_version: 'project-analysis-v1.1.0',
      status: 'COMPLETED',
      recommendations: [],
      warnings: [],
      evidence: [],
      trace_id: 'trace-1',
    }
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: status\ndata: {"message":"正在分析"}\n\n'))
        controller.enqueue(encoder.encode('event: delta\ndata: {"text":"流式"}\n\n'))
        controller.enqueue(encoder.encode('event: delta\ndata: {"text":"回答"}\n\n'))
        controller.enqueue(
          encoder.encode(`event: complete\ndata: ${JSON.stringify(complete)}\n\n`),
        )
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, body }))
    const statuses: string[] = []
    const deltas: string[] = []

    const result = await api.copilotStream('分析项目', undefined, {
      onStatus: (message) => statuses.push(message),
      onDelta: (text) => deltas.push(text),
    })

    expect(statuses).toEqual(['正在分析'])
    expect(deltas.join('')).toBe('流式回答')
    expect(result).toEqual(complete)
  })
})
