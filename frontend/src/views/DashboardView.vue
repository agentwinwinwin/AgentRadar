<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import EChart from '@/components/EChart.vue'
import ProjectTable from '@/components/ProjectTable.vue'
import type { DashboardData } from '@/types/api'
import { readDashboardCache, writeDashboardCache } from '@/utils/dashboardCache'
import { categoryLabel, lifecycleLabel } from '@/utils/labels'

const data = ref<DashboardData | null>(null)
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const cachedAt = ref<string | null>(null)
const trendExpanded = ref(true)
const potentialExpanded = ref(true)

const visibleTrendProjects = computed(() => (
  trendExpanded.value
    ? data.value?.top_trend_projects ?? []
    : []
))
const visiblePotentialProjects = computed(() => (
  potentialExpanded.value
    ? data.value?.high_potential_projects ?? []
    : []
))

const cacheLabel = computed(() => {
  if (!cachedAt.value) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(cachedAt.value))
})

const lifecycleOption = computed<EChartsOption>(() => ({
  grid: { left: 100, right: 30, top: 20, bottom: 30 },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'value' },
  yAxis: { type: 'category', data: data.value?.lifecycle_distribution.filter((item) => item.count).map((item) => lifecycleLabel(item.stage)) ?? [] },
  series: [{ type: 'bar', data: data.value?.lifecycle_distribution.filter((item) => item.count).map((item) => item.count) ?? [], itemStyle: { color: '#27a89a', borderRadius: [0, 6, 6, 0] } }],
}))

const categoryOption = computed<EChartsOption>(() => ({
  grid: { left: 120, right: 30, top: 20, bottom: 30 },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'value', max: data.value?.category_trend.status === 'READY' ? 100 : undefined },
  yAxis: {
    type: 'category',
    data: data.value?.category_trend.status === 'READY'
      ? data.value.category_trend.results.map((item) => categoryLabel(item.category))
      : data.value?.category_summary.map((item) => categoryLabel(item.category)) ?? [],
  },
  series: [{
    type: 'bar',
    data: data.value?.category_trend.status === 'READY'
      ? data.value.category_trend.results.map((item) => item.trend_score)
      : data.value?.category_summary.map((item) => item.repository_count) ?? [],
    itemStyle: { color: '#6d5dfc', borderRadius: [0, 6, 6, 0] },
  }],
}))

async function loadDashboard(force = false) {
  if (!force) {
    const cached = readDashboardCache()
    if (cached) {
      data.value = cached.data
      cachedAt.value = cached.cachedAt
      loading.value = false
      return
    }
  }

  if (data.value) refreshing.value = true
  else loading.value = true
  error.value = ''
  try {
    const result = await api.dashboard()
    const cached = writeDashboardCache(result)
    data.value = cached.data
    cachedAt.value = cached.cachedAt
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

onMounted(() => loadDashboard())
</script>

<template>
  <AppShell>
    <header class="hero hero-dashboard">
      <div>
        <p class="eyebrow">
          生态脉搏
        </p><h1>人工智能体开源趋势</h1><p>基于可验证的快照、活跃度与确定性趋势引擎。</p>
      </div><div class="hero-actions">
        <div
          v-if="cacheLabel"
          class="cache-status"
        >
          <span class="cache-status-dot" />
          数据更新于 {{ cacheLabel }}
        </div>
        <button
          class="button refresh-button"
          type="button"
          :disabled="refreshing"
          @click="loadDashboard(true)"
        >
          <span :class="{ spinning: refreshing }">↻</span>
          {{ refreshing ? '正在刷新' : '刷新数据' }}
        </button>
        <RouterLink
          class="button primary"
          to="/discover"
        >
          探索项目
        </RouterLink>
      </div>
    </header>
    <div
      v-if="loading"
      class="loading-state"
    >
      正在读取趋势数据…
    </div>
    <div
      v-else-if="error && !data"
      class="error-state"
    >
      {{ error }}
    </div>
    <template v-else-if="data">
      <p
        v-if="error"
        class="error-state compact-error dashboard-refresh-error"
      >
        刷新失败，当前继续展示上次缓存：{{ error }}
      </p>
      <section class="kpi-grid dashboard-kpis">
        <article><span>跟踪项目</span><strong>{{ data.statistics.tracked_projects }}</strong><small>项目总数</small></article>
        <article><span>活跃项目</span><strong>{{ data.statistics.active_projects }}</strong><small>30 日活跃</small></article>
        <article><span>新兴项目</span><strong>{{ data.statistics.emerging_projects }}</strong><small>早期上升</small></article>
        <article><span>突破项目</span><strong>{{ data.statistics.breakout_projects }}</strong><small>快速增长</small></article>
        <article><span>高潜力项目</span><strong>{{ data.statistics.high_potential_projects }}</strong><small>{{ data.high_potential_ranking?.source === 'STAR_FORECAST_V2' ? 'Star增强模型预测' : '当前确定性多信号评分' }}</small></article>
        <article><span>高炒作风险</span><strong>{{ data.statistics.high_hype_projects }}</strong><small>需谨慎关注</small></article>
      </section>
      <section class="dashboard-grid">
        <article class="panel wide ranking-panel trend-ranking-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">
                趋势排行
              </p><h2>趋势领先项目</h2>
            </div>
            <button
              v-if="data.top_trend_projects.length > 0"
              class="ranking-expand-button"
              type="button"
              :aria-expanded="trendExpanded"
              @click="trendExpanded = !trendExpanded"
            >
              {{ trendExpanded ? '收起全部' : '展开全部' }}
            </button>
          </div><ProjectTable
            v-if="trendExpanded || data.top_trend_projects.length === 0"
            :projects="visibleTrendProjects"
          />
        </article>
        <article class="panel wide ranking-panel potential-ranking-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">
                潜力排行
              </p><h2>高潜力项目</h2>
              <small>{{ data.high_potential_ranking?.source === 'STAR_FORECAST_V2'
                ? '评分为当前Star增强模型版本的预测百分位；缺少可靠输入的项目自动回退当前潜力评分'
                : 'Star增强模型尚未上线，当前使用确定性潜力评分' }}</small>
            </div>
            <button
              v-if="data.high_potential_projects.length > 0"
              class="ranking-expand-button"
              type="button"
              :aria-expanded="potentialExpanded"
              @click="potentialExpanded = !potentialExpanded"
            >
              {{ potentialExpanded ? '收起全部' : '展开全部' }}
            </button>
          </div><ProjectTable
            v-if="potentialExpanded || data.high_potential_projects.length === 0"
            :projects="visiblePotentialProjects"
          />
        </article>
        <article class="panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">
                阶段分布
              </p><h2>生命周期</h2>
            </div>
          </div><EChart
            :option="lifecycleOption"
            :empty="!data.lifecycle_distribution.some((item) => item.count)"
          />
        </article>
        <article class="panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">
                {{ data.category_trend.status === 'READY' ? '分类对比' : '数据积累中' }}
              </p><h2>{{ data.category_trend.status === 'READY' ? '分类趋势' : '分类项目分布' }}</h2>
              <small class="capability-note">
                {{ data.category_trend.status === 'READY'
                  ? `数据覆盖 ${Math.round(data.category_trend.data_coverage * 100)}%`
                  : '历史成熟后将自动切换为分类趋势，无需人工启用' }}
              </small>
            </div>
          </div><EChart
            :option="categoryOption"
            :empty="data.category_trend.status === 'READY'
              ? !data.category_trend.results.length
              : !data.category_summary.length"
          />
        </article>
      </section>
    </template>
  </AppShell>
</template>
