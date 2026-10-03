<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import { categoryLabel } from '@/utils/labels'
import type { WatchlistItem } from '@/types/api'

const items = ref<WatchlistItem[]>([])
const loading = ref(true)
const error = ref('')
const readyTrendCount = computed(() => items.value.filter((item) => item.repository.trend_score !== null).length)
const readyPotentialCount = computed(() => items.value.filter((item) => item.repository.potential_score !== null).length)

async function load() {
  try { items.value = (await api.watchlist()).results } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally { loading.value = false }
}
async function remove(id: number) { await api.unwatch(id); items.value = items.value.filter((item) => item.repository.id !== id) }
onMounted(load)
</script>

<template>
  <AppShell>
    <section class="workspace-header watchlist-header">
      <div>
        <p class="eyebrow">
          关注列表
        </p><h1>我的关注</h1><p>把需要持续观察的项目收进一个安静、清晰的研究空间。</p>
      </div>
      <span class="workspace-note">只影响个人工作区 · 不改变数据池</span>
    </section>
    <div
      v-if="loading"
      class="loading-state"
    >
      正在读取关注列表…
    </div>
    <div
      v-else-if="error"
      class="error-state"
    >
      {{ error }}
    </div>
    <div
      v-else-if="!items.length"
      class="empty-state panel"
    >
      尚未关注项目，可以从项目详情添加。
    </div>
    <section
      v-else
      class="watchlist-workspace"
    >
      <aside class="watchlist-summary">
        <span class="summary-glyph">♡</span>
        <p class="eyebrow">
          关注概览
        </p>
        <strong>{{ items.length }}</strong>
        <p>个持续观察项目</p>
        <dl>
          <div><dt>已有趋势信号</dt><dd>{{ readyTrendCount }}</dd></div>
          <div><dt>已有潜力信号</dt><dd>{{ readyPotentialCount }}</dd></div>
        </dl>
        <p class="summary-tip">
          进入项目详情，可查看完整指标、证据和最新动态。
        </p>
      </aside>
      <div class="watchlist-content">
        <div class="collection-heading">
          <div><h2>项目收藏册</h2><p>按关注时间持续维护你的研究清单</p></div>
          <span>{{ items.length }} 个项目</span>
        </div>
        <div class="watchlist-grid">
          <article
            v-for="item in items"
            :key="item.repository.id"
            class="watch-project"
          >
            <div class="watch-project-top">
              <span class="project-monogram">{{ item.repository.full_name.charAt(0).toUpperCase() }}</span>
              <span class="pill neutral">{{ categoryLabel(item.repository.category) }}</span>
            </div>
            <div class="watch-project-main">
              <RouterLink
                class="repo-link"
                :to="`/projects/${item.repository.id}`"
              >
                {{ item.repository.full_name }}
              </RouterLink>
              <small>关注于 {{ new Date(item.added_at).toLocaleDateString('zh-CN') }}</small>
            </div>
            <div class="watch-score-row">
              <div><span>趋势评分</span><strong>{{ item.repository.trend_score ?? '—' }}</strong></div>
              <div><span>潜力评分</span><strong>{{ item.repository.potential_score ?? '—' }}</strong></div>
            </div>
            <footer>
              <RouterLink :to="`/projects/${item.repository.id}`">
                查看项目 <span>→</span>
              </RouterLink>
              <button
                class="link-button"
                @click="remove(item.repository.id)"
              >
                取消关注
              </button>
            </footer>
          </article>
        </div>
      </div>
    </section>
  </AppShell>
</template>
