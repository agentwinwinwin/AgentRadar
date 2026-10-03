<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { isAuthenticated } from '@/auth/session'
import AppShell from '@/components/AppShell.vue'
import EChart from '@/components/EChart.vue'
import DeterministicScoreEvidence from '@/components/DeterministicScoreEvidence.vue'
import MetricValue from '@/components/MetricValue.vue'
import PotentialEvidence from '@/components/PotentialEvidence.vue'
import ScoreEvidence from '@/components/ScoreEvidence.vue'
import type { DeterministicScoreData, ForecastData, MetricsData, PotentialData, ProjectDetail, RepositoryCommunity, TrendData } from '@/types/api'
import { categoryLabel, hypeLabel, lifecycleLabel } from '@/utils/labels'

const route = useRoute()
const router = useRouter()
const repositoryId = Number(route.params.id)
const detail = ref<ProjectDetail | null>(null)
const metrics = ref<MetricsData | null>(null)
const trend = ref<TrendData | null>(null)
const potential = ref<PotentialData | null>(null)
const forecast = ref<ForecastData | null>(null)
const learning = ref<DeterministicScoreData | null>(null)
const enterprise = ref<DeterministicScoreData | null>(null)
const community = ref<RepositoryCommunity | null>(null)
const communityBusy = ref(false)
const communityError = ref('')
const range = ref<'7d' | '30d' | '90d'>('30d')
const loading = ref(true)
const error = ref('')
let localizationTimer: number | undefined
let localizationAttempts = 0
let forecastTimer: number | undefined
let forecastAttempts = 0

const forecastFeatureLabels: Record<string, string> = {
  current_stars: '当前星标数', current_forks: '当前复刻数',
  commit_7d: '近 7 天提交', commit_30d: '近 30 天提交',
  pr_created_7d: '近 7 天新建合并请求', pr_created_30d: '近 30 天新建合并请求',
  pr_merged_30d: '近 30 天已合并请求', issue_created_30d: '近 30 天新建议题',
  issue_closed_30d: '近 30 天已关闭议题', active_contributors_30d: '近 30 天活跃贡献者',
  release_count_30d: '近 30 天版本发布', days_since_last_push: '距上次推送天数',
  days_since_last_release: '距上次发布天数', community_health: '社区健康度',
  topic_momentum: '主题热度', repo_age_days: '项目年龄（天）', age_cohort: '项目年龄分组',
  category: '项目分类',
}
const forecastSignals = computed(() => Object.entries(forecast.value?.forecast?.input_features ?? {})
  .filter(([, value]) => value !== null)
  .slice(0, 8))

function forecastFeatureValue(key: string, value: string | number | null) {
  if (value === null) return '数据不足'
  if (typeof value === 'string') return value
  return Number.isInteger(value) ? value.toLocaleString('zh-CN') : value.toFixed(2)
}

const snapshotOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' }, legend: { data: ['星标数', '复刻数'], top: 0, left: 'center', itemGap: 20 }, grid: { left: 20, right: 20, top: 58, bottom: 22, containLabel: true }, xAxis: { type: 'category', axisLabel: { hideOverlap: true, margin: 14 }, data: metrics.value?.snapshots.map((item) => new Date(item.snapshot_at).toLocaleDateString('zh-CN')) ?? [] }, yAxis: { type: 'value' }, series: [{ name: '星标数', type: 'line', smooth: true, connectNulls: false, data: metrics.value?.snapshots.map((item) => item.stars) ?? [] }, { name: '复刻数', type: 'line', smooth: true, connectNulls: false, data: metrics.value?.snapshots.map((item) => item.forks) ?? [] }],
}))
const activityOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' }, legend: { data: ['代码提交', '新建合并请求', '活跃贡献者'], top: 0, left: 'center', itemGap: 16 }, grid: { left: 20, right: 20, top: 58, bottom: 22, containLabel: true }, xAxis: { type: 'category', axisLabel: { hideOverlap: true, margin: 14 }, data: metrics.value?.activity.map((item) => item.metric_date) ?? [] }, yAxis: { type: 'value' }, series: [{ name: '代码提交', type: 'bar', data: metrics.value?.activity.map((item) => item.commits_30d) ?? [] }, { name: '新建合并请求', type: 'line', data: metrics.value?.activity.map((item) => item.prs_created_30d) ?? [] }, { name: '活跃贡献者', type: 'line', data: metrics.value?.activity.map((item) => item.active_contributors_30d) ?? [] }],
}))
const trendOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' }, grid: { left: 55, right: 25, top: 30, bottom: 45 }, xAxis: { type: 'category', data: metrics.value?.trend_history.map((item) => item.algorithm_version) ?? [] }, yAxis: { type: 'value', min: 0, max: 100 }, series: [{ type: 'line', data: metrics.value?.trend_history.map((item) => item.trend_score) ?? [], itemStyle: { color: '#6d5dfc' } }],
}))
async function loadMetrics() { metrics.value = await api.metrics(repositoryId, range.value) }
function scheduleLocalizationRefresh() {
  if (detail.value?.localization_status !== 'PENDING' || localizationAttempts >= 20) return
  localizationTimer = window.setTimeout(async () => {
    localizationAttempts += 1
    try {
      detail.value = await api.project(repositoryId)
    } finally {
      scheduleLocalizationRefresh()
    }
  }, 3000)
}
function scheduleForecastRefresh() {
  if (forecast.value?.status !== 'PENDING' || forecastAttempts >= 20) return
  forecastTimer = window.setTimeout(async () => {
    forecastAttempts += 1
    try {
      forecast.value = await api.forecast(repositoryId)
    } finally {
      scheduleForecastRefresh()
    }
  }, 1500)
}
async function toggleWatch() {
  if (!detail.value) return
  if (!isAuthenticated.value) {
    await router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  if (detail.value.is_watchlisted) await api.unwatch(repositoryId)
  else await api.watch(repositoryId)
  detail.value.is_watchlisted = !detail.value.is_watchlisted
}
async function toggleLike() {
  if (!community.value) return
  if (!isAuthenticated.value) {
    await router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  communityBusy.value = true
  communityError.value = ''
  try {
    if (community.value.liked_by_me) {
      await api.unlike(repositoryId)
      community.value.liked_by_me = false
      community.value.like_count = Math.max(0, community.value.like_count - 1)
    } else {
      community.value = await api.like(repositoryId)
    }
  } catch (reason) {
    communityError.value = reason instanceof Error ? reason.message : '点赞操作失败'
  } finally {
    communityBusy.value = false
  }
}
async function load() {
  try {
    [detail.value, trend.value, potential.value, forecast.value, learning.value, enterprise.value, metrics.value, community.value] = await Promise.all([api.project(repositoryId), api.trend(repositoryId), api.potential(repositoryId), api.forecast(repositoryId), api.learning(repositoryId), api.enterprise(repositoryId), api.metrics(repositoryId, range.value), api.community(repositoryId)])
    scheduleLocalizationRefresh()
    scheduleForecastRefresh()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '加载失败' } finally { loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => {
  if (localizationTimer !== undefined) window.clearTimeout(localizationTimer)
  if (forecastTimer !== undefined) window.clearTimeout(forecastTimer)
})
</script>

<template>
  <AppShell>
    <div
      v-if="loading"
      class="loading-state"
    >
      正在读取项目数据…
    </div><div
      v-else-if="error"
      class="error-state"
    >
      {{ error }}
    </div>
    <template v-else-if="detail && trend && potential && forecast && learning && enterprise && metrics">
      <RouterLink
        class="detail-back-link"
        :to="{ name: 'discover' }"
      >
        <span aria-hidden="true">←</span> 返回发现项目
      </RouterLink>
      <header class="project-hero">
        <div>
          <p class="eyebrow">
            {{ categoryLabel(detail.category) }}
          </p><h1>{{ detail.full_name }}</h1><p>{{ detail.description_zh }}</p><small
            v-if="detail.localization_status === 'PENDING'"
            class="localization-pending"
          >正在后台生成中文翻译，完成后将自动更新</small><div class="tag-row">
            <span
              v-for="topic in detail.topics_zh"
              :key="topic"
              class="pill neutral"
            >{{ topic }}</span>
            <button
              class="watch-button"
              type="button"
              @click="toggleWatch"
            >
              {{ detail.is_watchlisted ? '取消关注' : '关注项目' }}
            </button>
            <a
              class="github-button"
              :href="detail.github_url"
              target="_blank"
              rel="noopener noreferrer"
            >前往 GitHub ↗</a>
            <button
              v-if="community"
              class="hero-community-button"
              :class="{ liked: community.liked_by_me }"
              type="button"
              :disabled="communityBusy"
              @click="toggleLike"
            >
              {{ community.liked_by_me ? '♥ 已点赞' : '♡ 点赞' }} · {{ community.like_count }}
            </button>
            <RouterLink
              v-if="community"
              class="hero-community-button comments"
              :to="{ name: 'project-comments', params: { id: repositoryId } }"
            >
              评论 · {{ community.comment_count }} →
            </RouterLink>
          </div>
        </div><div class="hero-score">
          <span>趋势评分</span><strong><MetricValue
            :value="detail.trend_score"
            :digits="1"
          /></strong><small>{{ lifecycleLabel(detail.lifecycle_stage) }}</small>
        </div>
      </header>
      <section
        v-if="community"
        class="community-spotlight"
      >
        <div class="community-spotlight-copy">
          <span class="community-symbol">聊</span>
          <div>
            <p class="eyebrow">
              项目讨论
            </p>
            <h2>{{ community.comment_count ? `${community.comment_count} 条公开评论` : '成为第一个评论的人' }}</h2>
            <p v-if="community.comments[0]">
              <strong>{{ community.comments[0].author.username }}</strong>：{{ community.comments[0].content }}
            </p>
            <p v-else>
              分享使用体验、技术判断或落地建议，所有人都能看到讨论。
            </p>
          </div>
        </div>
        <RouterLink
          class="button primary community-entry"
          :to="{ name: 'project-comments', params: { id: repositoryId } }"
        >
          {{ community.comment_count ? '查看全部评论' : '发布第一条评论' }} →
        </RouterLink>
      </section>
      <p
        v-if="communityError"
        class="error-state compact-error"
      >
        {{ communityError }}
      </p>
      <section class="kpi-grid detail-kpis">
        <article><span>星标数</span><strong><MetricValue :value="detail.stars" /></strong></article><article><span>复刻数</span><strong><MetricValue :value="detail.forks" /></strong></article><article>
          <span>社区健康度</span><strong><MetricValue
            :value="detail.community_health"
            suffix="%"
          /></strong>
        </article><article><span>数据完整度</span><strong>{{ Math.round(trend.data_completeness * 100) }}%</strong></article><article>
          <span>炒作风险</span><strong><MetricValue
            :value="trend.hype_risk"
            :digits="1"
          /></strong><small>{{ hypeLabel(trend.hype_risk_status) }}</small>
        </article><article>
          <span>潜力评分</span><strong><MetricValue
            :value="detail.potential_score"
            :digits="1"
          /></strong><small>{{ detail.potential_score_source === 'STAR_FORECAST_V2' ? 'Star增强模型预测百分位' : '当前确定性潜力' }}</small><small>置信度 {{ Math.round((detail.potential_confidence ?? 0) * 100) }}%</small>
        </article>
        <article>
          <span>学习价值</span><strong><MetricValue
            :value="learning.score"
            :digits="1"
          /></strong><small>置信度 {{ Math.round(learning.confidence * 100) }}%</small><small v-if="learning.score !== null && !learning.ranking_eligible">数据积累中</small>
        </article>
        <article>
          <span>企业成熟度</span><strong><MetricValue
            :value="enterprise.score"
            :digits="1"
          /></strong><small>置信度 {{ Math.round(enterprise.confidence * 100) }}%</small><small v-if="enterprise.score !== null && !enterprise.ranking_eligible">数据积累中</small>
        </article>
      </section>
      <section
        class="forecast-card"
        :class="{ ready: forecast.status === 'READY' && forecast.forecast }"
      >
        <div class="forecast-card-heading">
          <div>
            <p class="eyebrow">
              FORECAST V1 · 二分类模型
            </p>
            <h2>未来活跃增长预测</h2>
            <p>{{ forecast.definition }}</p>
          </div>
          <span
            class="forecast-status"
            :class="forecast.status === 'READY' ? 'is-ready' : 'is-accumulating'"
          >
            {{ forecast.status === 'READY' ? '预测已生成' : forecast.status === 'PENDING' ? '正在生成' : '数据积累中' }}
          </span>
        </div>
        <template v-if="forecast.status === 'READY' && forecast.forecast">
          <div class="forecast-card-content">
            <div class="forecast-primary">
              <span>进入高活跃增长组的概率</span>
              <strong>
                {{ Math.round(forecast.forecast.high_growth_probability * 1000) / 10 }}<small>%</small>
              </strong>
              <p>模型置信度 {{ Math.round(forecast.forecast.confidence * 100) }}%</p>
            </div>
            <div class="forecast-inputs">
              <div class="forecast-inputs-heading">
                <h3>本次预测输入</h3>
                <small>仅展示模型实际 Feature Snapshot 中可追溯的字段</small>
              </div>
              <div
                v-if="forecastSignals.length"
                class="forecast-signal-grid"
              >
                <div
                  v-for="([key, value]) in forecastSignals"
                  :key="key"
                >
                  <span>{{ forecastFeatureLabels[key] ?? key }}</span>
                  <strong>{{ forecastFeatureValue(key, value) }}</strong>
                </div>
              </div>
              <div
                v-else
                class="forecast-signal-empty"
              >
                该预测尚未保存可展示的输入快照
              </div>
              <div class="forecast-meta">
                <span>模型版本：{{ forecast.forecast.model_version }}</span>
                <span>预测周期：{{ forecast.forecast.forecast_horizon_days }} 天</span>
                <span>采样时间：{{ new Date(forecast.forecast.sample_at).toLocaleDateString('zh-CN') }}</span>
              </div>
            </div>
          </div>
          <p class="forecast-disclaimer">
            该概率只表示开发活跃增长分组，不代表爆火、Star 上涨或商业成功概率。Star 增强模型与本卡片相互独立。
          </p>
        </template>
        <div
          v-else
          class="forecast-waiting"
        >
          <strong>{{ forecast.status === 'PENDING' ? '正在后台生成本项目预测' : '模型尚未达到生产启用条件' }}</strong>
          <p v-if="forecast.status === 'PENDING'">
            页面无需等待模型计算，预测完成后本卡片会自动更新；同一模型版本再次访问将直接读取结果。
          </p>
          <p v-else>
            系统正在积累真实 Snapshot 和训练样本；通过训练、验证、独立测试并由管理员人工激活前，不展示模拟预测。
          </p>
          <small>当前继续使用确定性潜力评分</small>
        </div>
      </section>
      <div class="range-tabs">
        <button
          v-for="item in ['7d', '30d', '90d'] as const"
          :key="item"
          :class="{ active: range === item }"
          @click="range = item; loadMetrics()"
        >
          {{ item.replace('d', ' 天') }}
        </button>
      </div>
      <section class="dashboard-grid">
        <article class="panel">
          <div class="section-heading">
            <h2>星标与复刻快照</h2>
          </div><EChart
            :option="snapshotOption"
            :empty="!metrics.snapshots.length"
            empty-text="该时间范围内没有快照数据"
          />
        </article><article class="panel">
          <div class="section-heading">
            <h2>项目活跃度</h2>
          </div><EChart
            :option="activityOption"
            :empty="!metrics.activity.length"
            empty-text="该时间范围内没有活跃度数据"
          />
        </article><article class="panel wide">
          <div class="section-heading">
            <h2>趋势评分历史</h2>
          </div><EChart
            :option="trendOption"
            :empty="!metrics.trend_history.length"
            empty-text="尚无趋势评分记录"
          />
        </article>
      </section>
      <ScoreEvidence :trend="trend" />
      <PotentialEvidence :potential="potential" />
      <DeterministicScoreEvidence
        title="为什么获得这个学习价值评分"
        :score="learning"
      />
      <DeterministicScoreEvidence
        title="为什么获得这个企业成熟度评分"
        :score="enterprise"
      />
    </template>
  </AppShell>
</template>
