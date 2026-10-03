<script setup lang="ts">
import MetricValue from '@/components/MetricValue.vue'
import type { PotentialData } from '@/types/api'
import { evidenceLabel, hypeLabel } from '@/utils/labels'

defineProps<{ potential: PotentialData }>()

const inputLabels: Record<string, string> = {
  trend: '趋势评分',
  momentum: '增长动量',
  topic_momentum: '主题热度',
  community: '社区活跃度',
  delivery: '交付能力',
  novelty: '创新度',
  hype_risk: '炒作风险',
}
</script>

<template>
  <section class="panel evidence-panel">
    <div class="section-heading">
      <div>
        <p class="eyebrow">
          确定性潜力依据
        </p><h2>当前多信号潜力评分说明</h2>
      </div>
      <span class="version">{{ potential.algorithm_version }}</span>
    </div>
    <div
      v-if="potential.status === 'NOT_AVAILABLE'"
      class="empty-state"
    >
      尚无潜力评分数据
    </div>
    <template v-else-if="potential.evidence">
      <div class="score-grid potential-grid">
        <article
          v-for="(value, key) in potential.evidence.inputs"
          :key="key"
          class="score-item"
        >
          <span>{{ inputLabels[String(key)] ?? evidenceLabel(String(key)) }}</span>
          <strong><MetricValue
            :value="value"
            :digits="1"
          /></strong>
          <small>权重 {{ Math.round((potential.evidence.weights[String(key)] ?? 0) * 100) }}%</small>
        </article>
      </div>
      <div class="evidence-meta">
        <p>
          <strong>基础潜力：</strong><MetricValue
            :value="potential.evidence.base_potential"
            :digits="1"
          />
        </p>
        <p><strong>炒作风险处理：</strong>{{ hypeLabel(potential.evidence.hype_risk_status) }}；扣分 {{ potential.evidence.hype_penalty.toFixed(1) }}</p>
        <p><strong>置信度：</strong>{{ Math.round(potential.confidence * 100) }}%</p>
        <p><strong>候选状态：</strong>{{ potential.breakout_candidate ? '突破候选' : potential.high_potential ? '高潜力项目' : potential.potential_candidate ? '潜力候选' : '未达到候选门槛' }}</p>
        <p v-if="potential.evidence.missing_inputs.length">
          <strong>数据不足：</strong>{{ potential.evidence.missing_inputs.map((item) => inputLabels[item] ?? evidenceLabel(item)).join('、') }}
        </p>
      </div>
    </template>
  </section>
</template>
