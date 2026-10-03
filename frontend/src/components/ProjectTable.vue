<script setup lang="ts">
import MetricValue from '@/components/MetricValue.vue'
import type { ProjectSummary } from '@/types/api'
import { categoryLabel, lifecycleLabel } from '@/utils/labels'

withDefaults(defineProps<{
  projects: ProjectSummary[]
  showWatchStatus?: boolean
  watchedIds?: Set<number>
  watchlistReady?: boolean
}>(), {
  showWatchStatus: false,
  watchedIds: () => new Set<number>(),
  watchlistReady: true,
})

const MIN_POTENTIAL_RANKING_CONFIDENCE = 0.45
</script>

<template>
  <div
    v-if="projects.length"
    class="table-wrap"
  >
    <table>
      <thead><tr><th>代码仓库</th><th>分类</th><th>星标数</th><th>趋势评分</th><th>潜力评分</th><th>学习价值</th><th>企业成熟度</th><th>生命周期</th></tr></thead>
      <tbody>
        <tr
          v-for="project in projects"
          :key="project.id"
        >
          <td>
            <RouterLink
              class="repo-link"
              :to="`/projects/${project.id}`"
            >
              {{ project.full_name }}
            </RouterLink>
            <small>{{ project.primary_language ?? '语言未知' }}</small>
            <span
              v-if="showWatchStatus"
              class="watch-status"
              :class="{ watched: watchedIds.has(project.id) }"
            >
              {{ watchlistReady ? (watchedIds.has(project.id) ? '♥ 已关注' : '♡ 未关注') : '正在读取关注状态' }}
            </span>
          </td>
          <td><span class="pill neutral">{{ categoryLabel(project.category) }}</span></td>
          <td><MetricValue :value="project.stars" /></td>
          <td>
            <MetricValue
              :value="project.trend_score"
              :digits="1"
            />
          </td>
          <td>
            <span v-if="project.potential_confidence !== null && project.potential_confidence < MIN_POTENTIAL_RANKING_CONFIDENCE">数据不足</span>
            <MetricValue
              v-else
              :value="project.potential_score"
              :digits="1"
            />
            <small v-if="project.potential_confidence !== null">
              置信度 {{ Math.round(project.potential_confidence * 100) }}%
            </small>
            <small v-if="project.potential_score_source === 'STAR_FORECAST_V2'">
              Star增强模型预测百分位
            </small>
            <small v-else>
              当前确定性潜力
            </small>
          </td>
          <td>
            <MetricValue
              :value="project.learning_score"
              :digits="1"
            /><small v-if="project.learning_confidence !== null">置信度 {{ Math.round(project.learning_confidence * 100) }}%</small>
            <small v-if="project.learning_score !== null && project.learning_confidence !== null && project.learning_confidence < 0.6">数据积累中</small>
          </td>
          <td>
            <MetricValue
              :value="project.enterprise_score"
              :digits="1"
            /><small v-if="project.enterprise_confidence !== null">置信度 {{ Math.round(project.enterprise_confidence * 100) }}%</small>
            <small v-if="project.enterprise_score !== null && project.enterprise_confidence !== null && project.enterprise_confidence < 0.6">数据积累中</small>
          </td>
          <td>{{ lifecycleLabel(project.lifecycle_stage) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <div
    v-else
    class="empty-state"
  >
    暂无符合条件的项目
  </div>
</template>
