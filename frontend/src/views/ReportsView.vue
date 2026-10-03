<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import type { ScheduledReportData } from '@/types/api'

const reports = ref<ScheduledReportData[]>([])
const loading = ref(true)
const selectedId = ref<number | null>(null)
const selectedReport = computed(() => reports.value.find((report) => report.id === selectedId.value) ?? reports.value[0])
async function load() { reports.value = (await api.reports()).results; loading.value = false }
async function generate(type: 'DAILY' | 'WEEKLY') { const report = await api.generateReport(type); reports.value = [report, ...reports.value.filter((item) => item.id !== report.id)]; selectedId.value = report.id }
onMounted(load)
</script>

<template>
  <AppShell>
    <section class="workspace-header reports-header">
      <div>
        <p class="eyebrow">
          定期报告
        </p><h1>项目情报简报</h1><p>把新项目、关注变化和风险信号整理成可快速阅读的日报与周报。</p>
      </div><div class="report-actions">
        <button
          class="button primary"
          @click="generate('DAILY')"
        >
          生成日报
        </button><button
          class="button"
          @click="generate('WEEKLY')"
        >
          生成周报
        </button>
      </div>
    </section>
    <div
      v-if="loading"
      class="loading-state"
    >
      正在读取报告…
    </div>
    <div
      v-else-if="!reports.length"
      class="empty-state panel"
    >
      尚无报告。
    </div>
    <section
      v-else
      class="reports-workspace"
    >
      <aside class="report-index">
        <header><span>▤</span><div><strong>报告档案</strong><small>共 {{ reports.length }} 份</small></div></header>
        <button
          v-for="report in reports"
          :key="report.id"
          :class="{ active: selectedReport?.id === report.id }"
          @click="selectedId = report.id"
        >
          <span>{{ report.report_type === 'DAILY' ? '日报' : '周报' }}</span>
          <strong>{{ new Date(report.period_end).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' }) }}</strong>
          <small>{{ report.content.alerts.length }} 条提醒 · {{ report.content.new_repositories.length }} 个新项目</small>
        </button>
        <div class="report-source-note">
          <strong>事实来源</strong><p>结构化数据库与现有 Evidence，评分不由 LLM 重算。</p>
        </div>
      </aside>
      <article
        v-if="selectedReport"
        class="report-reader"
      >
        <header class="report-cover">
          <div><span>{{ selectedReport.report_type === 'DAILY' ? 'DAILY BRIEF' : 'WEEKLY BRIEF' }}</span><h2>{{ new Date(selectedReport.period_end).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }) }}</h2><p>{{ new Date(selectedReport.period_start).toLocaleDateString('zh-CN') }} — {{ new Date(selectedReport.period_end).toLocaleDateString('zh-CN') }}</p></div>
          <span class="version">{{ selectedReport.rule_version }}</span>
        </header>
        <div class="report-grid editorial-report-grid">
          <div><span>新发现项目</span><strong>{{ selectedReport.content.new_repositories.length }}</strong><small>进入观察范围</small></div>
          <div><span>关注变化</span><strong>{{ selectedReport.content.watchlist_changes.length }}</strong><small>个人列表动态</small></div>
          <div><span>项目提醒</span><strong>{{ selectedReport.content.alerts.length }}</strong><small>规则触发信号</small></div>
          <div><span>证据不足</span><strong>{{ selectedReport.content.insufficient_evidence.length }}</strong><small>仍在积累数据</small></div>
        </div>
        <section class="report-section">
          <div class="report-section-heading">
            <span>01</span><div><h3>本期观察</h3><p>值得快速浏览的结构化变化</p></div>
          </div>
          <div class="report-fact-row">
            <span>新增 Agent Repository</span><strong>{{ selectedReport.content.new_repositories.length }}</strong>
          </div>
          <div class="report-fact-row">
            <span>Watchlist 变化</span><strong>{{ selectedReport.content.watchlist_changes.length }}</strong>
          </div>
          <div class="report-fact-row">
            <span>触发提醒</span><strong>{{ selectedReport.content.alerts.length }}</strong>
          </div>
        </section>
        <section class="report-section muted-section">
          <div class="report-section-heading">
            <span>02</span><div><h3>数据成熟度说明</h3><p>这些项目暂时无法形成可靠判断</p></div>
          </div>
          <details><summary>查看证据不足项（{{ selectedReport.content.insufficient_evidence.length }}）</summary><pre>{{ JSON.stringify(selectedReport.content.insufficient_evidence, null, 2) }}</pre></details>
        </section>
        <footer class="report-footer">
          <span>生成于 {{ new Date(selectedReport.generated_at).toLocaleString('zh-CN') }}</span><strong>结构化事实生成 · 未使用 LLM 计算</strong>
        </footer>
      </article>
    </section>
  </AppShell>
</template>
