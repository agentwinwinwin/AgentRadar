<script setup lang="ts">
import MetricValue from '@/components/MetricValue.vue'
import type { TrendData } from '@/types/api'
import { ageLabel, categoryLabel, evidenceLabel } from '@/utils/labels'

defineProps<{ trend: TrendData }>()

</script>

<template>
  <section class="panel evidence-panel">
    <div class="section-heading">
      <div>
        <p class="eyebrow">
          评分说明
        </p><h2>评分依据</h2>
      </div><span class="version">{{ trend.algorithm_version ?? '版本不可用' }}</span>
    </div>
    <div
      v-if="trend.status === 'NOT_AVAILABLE'"
      class="empty-state"
    >
      尚无趋势评分数据
    </div>
    <template v-else>
      <div class="score-grid">
        <article
          v-for="(component, key) in trend.evidence?.components"
          :key="key"
          class="score-item"
        >
          <span>{{ evidenceLabel(String(key)) }}</span>
          <strong><MetricValue
            :value="component.score"
            :digits="1"
          /></strong>
          <small>完整度 {{ Math.round(component.completeness * 100) }}%</small>
        </article>
      </div>
      <div class="evidence-meta">
        <p><strong>对比群组：</strong>{{ categoryLabel(trend.evidence?.cohort?.category) }} · {{ ageLabel(trend.evidence?.cohort?.age) }} · {{ trend.evidence?.cohort_size ?? 0 }} 个项目</p>
        <p><strong>整体完整度：</strong>{{ Math.round(trend.data_completeness * 100) }}%</p>
        <p v-if="trend.evidence?.missing_inputs?.length">
          <strong>缺失输入：</strong>{{ trend.evidence.missing_inputs.map(evidenceLabel).join('、') }}
        </p>
      </div>
    </template>
  </section>
</template>
