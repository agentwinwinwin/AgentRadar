<script setup lang="ts">
const props = withDefaults(
  defineProps<{ value: number | null | undefined; digits?: number; suffix?: string }>(),
  { digits: 0, suffix: '' },
)

function display(): string {
  if (props.value === null || props.value === undefined) return '数据不足'
  return `${props.value.toLocaleString('zh-CN', {
    minimumFractionDigits: props.digits,
    maximumFractionDigits: props.digits,
  })}${props.suffix}`
}
</script>

<template>
  <span :class="{ 'is-missing': value === null || value === undefined }">{{ display() }}</span>
</template>

