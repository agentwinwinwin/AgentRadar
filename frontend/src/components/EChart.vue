<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ option: EChartsOption; empty?: boolean; emptyText?: string }>()
const chartRoot = ref<HTMLDivElement | null>(null)
use([GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

let chart: EChartsType | null = null

function render() {
  if (!chart || props.empty) return
  chart.setOption(props.option, true)
}

function resize() {
  chart?.resize()
}

onMounted(async () => {
  await Promise.all([import('@/charts/bar'), import('@/charts/line')])
  if (chartRoot.value) {
    chart = init(chartRoot.value)
    render()
    window.addEventListener('resize', resize)
  }
})

watch(() => props.option, render, { deep: true })
watch(
  () => props.empty,
  (empty) => {
    if (!empty) render()
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
})
</script>

<template>
  <div class="chart-frame">
    <div
      v-show="!empty"
      ref="chartRoot"
      class="chart-canvas"
    />
    <div
      v-if="empty"
      class="empty-state"
    >
      {{ emptyText ?? '数据不足' }}
    </div>
  </div>
</template>
