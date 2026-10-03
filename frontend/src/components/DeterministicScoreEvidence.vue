<script setup lang="ts">
import MetricValue from '@/components/MetricValue.vue'
import type { DeterministicScoreData } from '@/types/api'
import { evidenceLabel } from '@/utils/labels'

defineProps<{ title: string; score: DeterministicScoreData }>()

const knowledgeLabel: Record<string, string> = {
  INGESTED: '知识文档已采集',
  NOT_INGESTED: '知识文档尚未采集',
  DOCUMENT_NOT_FOUND: '已采集但未找到相关文档',
}
</script>

<template>
  <section class="panel evidence-panel">
    <div class="section-heading">
      <div>
        <p class="eyebrow">
          确定性评分
        </p><h2>{{ title }}</h2>
      </div>
      <span class="version">{{ score.algorithm_version }}</span>
    </div>
    <div
      v-if="score.status === 'NOT_AVAILABLE'"
      class="empty-state"
    >
      数据积累中
    </div>
    <template v-else>
      <p>
        <strong>评分：</strong><MetricValue
          :value="score.score"
          :digits="1"
        />
      </p>
      <p><strong>置信度：</strong>{{ Math.round(score.confidence * 100) }}%</p>
      <p v-if="!score.ranking_eligible">
        <strong>排名状态：</strong>数据积累中 / 数据不足
      </p>
      <p v-if="score.recommendation">
        <strong>采用建议：</strong>{{ score.recommendation }}
      </p>
      <p v-if="score.evidence">
        <strong>知识状态：</strong>{{ knowledgeLabel[score.evidence.knowledge_status] }}
      </p>
      <div
        v-if="score.evidence"
        class="score-grid"
      >
        <article
          v-for="(component, key) in score.evidence.components"
          :key="key"
        >
          <span>{{ evidenceLabel(String(key)) }}</span>
          <strong><MetricValue
            :value="component.value"
            :digits="1"
          /></strong>
          <small>{{ component.status === 'VALUE' ? `权重 ${score.evidence.weights[String(key)]}%` : '数据缺失' }}</small>
        </article>
      </div>
    </template>
  </section>
</template>
