<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import type {
  CopilotEvidence,
  CopilotHistorySummary,
  CopilotResponse,
} from '@/types/api'

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  result?: CopilotResponse
}

const suggestions = [
  { icon: '↗', label: '趋势研究', text: '最近哪些智能体框架值得关注？' },
  { icon: '⌘', label: '学习选型', text: '推荐适合学习的编码智能体项目' },
  { icon: '◇', label: '企业评估', text: '哪些多智能体项目更适合企业试用？' },
  { icon: '◎', label: '项目分析', text: '分析 langchain-ai/langgraph' },
]
const input = ref('')
const loading = ref(false)
const streamStatus = ref('')
const error = ref('')
const messages = ref<ChatMessage[]>([])
const sessionId = ref(window.localStorage.getItem('agentradar-copilot-session') ?? undefined)
const history = ref<CopilotHistorySummary[]>([])
const selectedHistoryId = ref<number | null>(null)
const historyLoading = ref(false)

function structuredEvidence(evidence: CopilotEvidence[]) {
  return evidence.filter((item) => item.source_type === 'STRUCTURED_TOOL_EVIDENCE')
}

function documentEvidence(evidence: CopilotEvidence[]) {
  const groups = new Map<string, { repository?: string; title: string; url?: string | null; sourceType: string; snippets: string[] }>()
  for (const item of evidence.filter((entry) => entry.source_type !== 'STRUCTURED_TOOL_EVIDENCE')) {
    const key = `${item.repository ?? ''}|${item.url ?? item.path ?? item.title ?? item.source_type}`
    const group = groups.get(key) ?? {
      repository: item.repository,
      title: item.title || item.path || '项目文档',
      url: item.url,
      sourceType: item.source_type,
      snippets: [],
    }
    if (item.snippet && group.snippets.length < 3) group.snippets.push(cleanSnippet(item.snippet))
    groups.set(key, group)
  }
  return [...groups.values()]
}

function cleanSnippet(value: string) {
  return value
    .replace(/```[\w-]*|```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/(^|\s)[#>*`|_-]+(?=\s|$)/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 260)
}

function answerSegments(message: ChatMessage) {
  const links = new Map(
    (message.result?.repository_links ?? []).map((item) => [item.full_name, item.repository_id]),
  )
  if (!links.size) return [{ text: message.text, repositoryId: null }]
  const names = [...links.keys()].sort((left, right) => right.length - left.length)
  const escaped = names.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const matcher = new RegExp(`(${escaped.join('|')})`, 'g')
  return message.text.split(matcher).filter(Boolean).map((text) => ({
    text,
    repositoryId: links.get(text) ?? null,
  }))
}

async function send(text = input.value) {
  const question = text.trim()
  if (!question || loading.value) return
  messages.value.push({ role: 'user', text: question })
  input.value = ''
  error.value = ''
  loading.value = true
  streamStatus.value = '正在连接分析工作流…'
  const assistantMessage: ChatMessage = { role: 'assistant', text: '' }
  messages.value.push(assistantMessage)
  try {
    const result = await api.copilotStream(question, sessionId.value, {
      onStatus: (message) => { streamStatus.value = message },
      onDelta: (chunk) => { assistantMessage.text += chunk },
    })
    assistantMessage.text ||= result.answer
    assistantMessage.result = result
    sessionId.value = result.session_id
    window.localStorage.setItem('agentradar-copilot-session', result.session_id)
    await loadHistory()
  } catch (reason) {
    messages.value = messages.value.filter((message) => message !== assistantMessage)
    error.value = reason instanceof Error ? reason.message : '智能分析暂时不可用'
  } finally {
    loading.value = false
    streamStatus.value = ''
  }
}

async function loadHistory() {
  try {
    history.value = (await api.copilotHistory()).results
    selectedHistoryId.value =
      history.value.find((item) => item.session_id === sessionId.value)?.id ?? null
  } catch {
    history.value = []
  }
}

async function openHistory(id: number) {
  if (loading.value) return
  historyLoading.value = true
  error.value = ''
  try {
    const detail = await api.copilotHistoryDetail(id)
    messages.value = detail.messages.map((message) => ({
      role: message.role === 'USER' ? 'user' : 'assistant',
      text: message.content,
      result: message.response ?? undefined,
    }))
    selectedHistoryId.value = id
    sessionId.value = detail.session_id
    window.localStorage.setItem('agentradar-copilot-session', detail.session_id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '历史会话加载失败'
  } finally {
    historyLoading.value = false
  }
}

function newConversation() {
  if (loading.value) return
  messages.value = []
  selectedHistoryId.value = null
  sessionId.value = undefined
  window.localStorage.removeItem('agentradar-copilot-session')
}

async function deleteHistory(id: number) {
  if (loading.value) return
  if (!window.confirm('确定删除这条历史会话吗？删除后无法恢复。')) return
  try {
    await api.deleteCopilotHistory(id)
    if (selectedHistoryId.value === id) newConversation()
    await loadHistory()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '历史会话删除失败'
  }
}

onMounted(loadHistory)
</script>

<template>
  <AppShell>
    <section class="copilot-header">
      <div>
        <p class="eyebrow">
          AgentRadar Intelligence
        </p>
        <h1>智能分析工作台</h1>
        <p>把项目、赛道或选型目标交给我，用真实数据和可追溯证据给出判断。</p>
      </div>
      <div class="copilot-trust">
        <span />只读分析 · 证据可追溯
      </div>
    </section>

    <section class="copilot-layout">
      <aside class="suggestion-panel">
        <section class="copilot-history">
          <header>
            <div><span>历史记录</span><small>保留未删除的问题与回答</small></div>
            <button
              type="button"
              class="new-chat-button"
              @click="newConversation"
            >
              +新对话
            </button>
          </header>
          <div class="history-list">
            <p
              v-if="historyLoading"
              class="history-empty"
            >
              正在加载历史记录…
            </p>
            <p
              v-else-if="history.length === 0"
              class="history-empty"
            >
              暂无历史记录
            </p>
            <template v-else>
              <article
                v-for="item in history"
                :key="item.id"
                :class="{ active: selectedHistoryId === item.id }"
              >
                <button
                  type="button"
                  class="history-open"
                  @click="openHistory(item.id)"
                >
                  <strong>{{ item.title }}</strong>
                  <small>{{ item.message_count / 2 }} 轮对话</small>
                </button>
                <button
                  type="button"
                  class="history-delete"
                  :aria-label="`删除历史会话 ${item.title}`"
                  @click="deleteHistory(item.id)"
                >
                  ×
                </button>
              </article>
            </template>
          </div>
        </section>
        <div class="suggestion-heading">
          <span class="suggestion-orbit">✦</span>
          <div><h2>从一个目标开始</h2><p>选择常用分析路径，或直接输入你的问题。</p></div>
        </div>
        <button
          v-for="suggestion in suggestions"
          :key="suggestion.text"
          type="button"
          @click="send(suggestion.text)"
        >
          <span class="suggestion-icon">{{ suggestion.icon }}</span>
          <span><small>{{ suggestion.label }}</small><strong>{{ suggestion.text }}</strong></span>
          <span class="suggestion-arrow">→</span>
        </button>
        <div class="copilot-boundary">
          <strong>分析边界</strong>
          <p>评分来自确定性引擎，知识结论附带来源；证据不足时不会猜测。</p>
        </div>
      </aside>

      <div class="chat-panel">
        <header class="chat-toolbar">
          <div><span class="assistant-avatar">AR</span><div><strong>AgentRadar 分析助手</strong><small>结构化数据 · 项目知识库 · 决策工作流</small></div></div>
          <span class="online-status">在线</span>
        </header>
        <div class="chat-scroll">
          <div
            v-if="messages.length === 0"
            class="copilot-empty"
          >
            <span class="empty-glyph">✦</span>
            <h2>今天想研究什么？</h2>
            <p>可以比较项目、研究赛道、判断学习价值，或评估企业采用风险。</p>
          </div>
          <article
            v-for="(message, index) in messages"
            :key="index"
            class="chat-message"
            :class="message.role"
          >
            <span class="message-avatar">{{ message.role === 'user' ? '你' : 'AR' }}</span>
            <div class="message-body">
              <span>{{ message.role === 'user' ? '你' : 'AgentRadar' }}</span>
              <p>
                <template
                  v-for="(segment, segmentIndex) in answerSegments(message)"
                  :key="segmentIndex"
                >
                  <RouterLink
                    v-if="segment.repositoryId"
                    class="answer-project-link"
                    :to="`/projects/${segment.repositoryId}`"
                  >
                    {{ segment.text }}
                  </RouterLink><template v-else>
                    {{ segment.text }}
                  </template>
                </template>
              </p>
              <template v-if="message.result">
                <div class="agent-meta">
                  <small>意图置信度 {{ Math.round(message.result.intent_confidence * 100) }}%</small>
                  <small>{{ message.result.skill_version }}</small>
                  <small>状态：{{ message.result.status }}</small>
                </div>
                <p
                  v-if="message.result.warnings.length"
                  class="agent-warning"
                >
                  提示：{{ message.result.warnings.join('；') }}
                </p>
                <details v-if="message.result.evidence.length">
                  <summary>查看证据（{{ structuredEvidence(message.result.evidence).length }} 项指标 · {{ documentEvidence(message.result.evidence).length }} 个文档来源）</summary>
                  <div class="copilot-evidence-panel">
                    <section v-if="structuredEvidence(message.result.evidence).length">
                      <header><span>◫</span><div><strong>结构化指标</strong><small>来自 AgentRadar 数据库与确定性引擎</small></div></header>
                      <div class="structured-evidence-grid">
                        <article
                          v-for="(evidence, evidenceIndex) in structuredEvidence(message.result.evidence)"
                          :key="`structured-${evidenceIndex}`"
                        >
                          <strong>{{ evidence.title || '结构化系统证据' }}</strong>
                          <span v-if="evidence.algorithm_version">{{ evidence.algorithm_version }}</span>
                          <small v-if="evidence.confidence != null">数据完整度 {{ Math.round(evidence.confidence * 100) }}%</small>
                        </article>
                      </div>
                    </section>
                    <section v-if="documentEvidence(message.result.evidence).length">
                      <header><span>▤</span><div><strong>项目文档</strong><small>来自项目知识库，已合并相同来源</small></div></header>
                      <article
                        v-for="(group, groupIndex) in documentEvidence(message.result.evidence)"
                        :key="`document-${groupIndex}`"
                        class="document-evidence-card"
                      >
                        <div><span>{{ group.sourceType }}</span><strong>{{ group.title }}</strong><small v-if="group.repository">{{ group.repository }}</small></div>
                        <p
                          v-for="(snippet, snippetIndex) in group.snippets"
                          :key="snippetIndex"
                        >
                          {{ snippet }}<span v-if="snippet.length >= 260">…</span>
                        </p>
                        <a
                          v-if="group.url"
                          :href="group.url"
                          target="_blank"
                          rel="noreferrer"
                        >查看原始文档 ↗</a>
                      </article>
                    </section>
                  </div>
                </details>
              </template>
            </div>
          </article>
          <div
            v-if="loading"
            class="agent-thinking"
          >
            <span />{{ streamStatus }}
          </div>
          <p
            v-if="error"
            class="error-state compact-error"
          >
            {{ error }}
          </p>
        </div>
        <form
          class="chat-input"
          @submit.prevent="send()"
        >
          <div class="composer-label">
            <span>✦</span>向分析助手提问
          </div>
          <textarea
            v-model="input"
            maxlength="4000"
            rows="3"
            placeholder="例如：比较两个项目的学习价值与企业采用风险"
            aria-label="向智能分析助手提问"
          />
          <div class="composer-footer">
            <small>Enter 发送 · 最多 4000 字</small>
            <button
              class="button primary"
              type="submit"
              :disabled="loading || !input.trim()"
            >
              发送 <span>↑</span>
            </button>
          </div>
        </form>
      </div>
    </section>
  </AppShell>
</template>
