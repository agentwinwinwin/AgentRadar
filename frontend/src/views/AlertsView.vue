<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import type { AlertData } from '@/types/api'

const alerts = ref<AlertData[]>([])
const loading = ref(true)
const filter = ref<'ALL' | 'UNREAD'>('ALL')
const unreadCount = computed(() => alerts.value.filter((alert) => alert.status === 'UNREAD').length)
const visibleAlerts = computed(() => filter.value === 'UNREAD' ? alerts.value.filter((alert) => alert.status === 'UNREAD') : alerts.value)
const severityLabel = { INFO: '信息', WARNING: '注意', CRITICAL: '重要' }
async function load() { alerts.value = (await api.alerts()).results; loading.value = false }
async function markRead(alert: AlertData) { if (alert.status === 'UNREAD') Object.assign(alert, await api.updateAlert(alert.id, 'READ')) }
onMounted(load)
</script>

<template>
  <AppShell>
    <section class="workspace-header alerts-header">
      <div>
        <p class="eyebrow">
          确定性提醒
        </p><h1>动态提醒</h1><p>像处理收件箱一样阅读项目变化，每条结论都有真实证据。</p>
      </div>
      <span class="workspace-note danger-note">规则触发 · 非 LLM 判断</span>
    </section>
    <div
      v-if="loading"
      class="loading-state"
    >
      正在读取提醒…
    </div>
    <div
      v-else-if="!alerts.length"
      class="empty-state panel"
    >
      当前没有符合数据门禁的提醒。
    </div>
    <section
      v-else
      class="alerts-workspace"
    >
      <aside class="alert-inbox-nav">
        <div class="inbox-heading">
          <span>◉</span><div><strong>提醒收件箱</strong><small>{{ unreadCount }} 条未读</small></div>
        </div>
        <button
          :class="{ active: filter === 'ALL' }"
          @click="filter = 'ALL'"
        >
          <span>全部动态</span><strong>{{ alerts.length }}</strong>
        </button>
        <button
          :class="{ active: filter === 'UNREAD' }"
          @click="filter = 'UNREAD'"
        >
          <span>未读提醒</span><strong>{{ unreadCount }}</strong>
        </button>
        <div class="alert-rule-note">
          <strong>可信提醒</strong><p>历史不足或置信度未达门槛时，系统不会产生虚假提醒。</p>
        </div>
      </aside>
      <div class="alert-stream">
        <header><div><h2>{{ filter === 'UNREAD' ? '未读提醒' : '全部动态' }}</h2><p>按检测时间从新到旧排列</p></div><span>{{ visibleAlerts.length }} 条</span></header>
        <article
          v-for="alert in visibleAlerts"
          :key="alert.id"
          class="alert-event"
          :class="[{ unread: alert.status === 'UNREAD' }, `severity-${alert.severity.toLowerCase()}`]"
          @click="markRead(alert)"
        >
          <span class="event-rail"><i /></span>
          <div class="event-content">
            <div class="event-meta">
              <span>{{ severityLabel[alert.severity] }}</span><time>{{ new Date(alert.detected_at).toLocaleString('zh-CN') }}</time>
            </div>
            <h2>{{ alert.title }}</h2>
            <RouterLink
              class="repo-link"
              :to="`/projects/${alert.repository.id}`"
            >
              {{ alert.repository.full_name }} <span>↗</span>
            </RouterLink>
            <details><summary>查看证据 · 触发依据</summary><pre>{{ JSON.stringify(alert.evidence, null, 2) }}</pre></details>
            <footer><span>{{ alert.rule_version }}</span><strong>{{ alert.status === 'UNREAD' ? '未读' : '已读' }}</strong></footer>
          </div>
        </article>
        <div
          v-if="!visibleAlerts.length"
          class="stream-empty"
        >
          没有未读提醒，收件箱已经清空。
        </div>
      </div>
    </section>
  </AppShell>
</template>
