<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { api } from '@/api/client'
import { isAuthenticated } from '@/auth/session'
import AppShell from '@/components/AppShell.vue'
import ProjectTable from '@/components/ProjectTable.vue'
import type { PaginatedProjects } from '@/types/api'

const result = ref<PaginatedProjects | null>(null)
const loading = ref(false)
const error = ref('')
const page = ref(1)
const filters = reactive({ q: '', category: '', language: '', potentialMin: '', sort: '-trend' })
const watchedIds = ref<Set<number>>(new Set())
const watchlistReady = ref(false)

async function loadWatchlist() {
  if (!isAuthenticated.value) {
    watchlistReady.value = true
    return
  }
  try {
    const response = await api.watchlist()
    watchedIds.value = new Set(response.results.map((item) => item.repository.id))
  } catch {
    watchedIds.value = new Set()
  } finally {
    watchlistReady.value = true
  }
}

async function load(targetPage = 1) {
  loading.value = true
  error.value = ''
  page.value = targetPage
  const params = new URLSearchParams({ page: String(page.value), page_size: '20', sort: filters.sort })
  if (filters.q) params.set('q', filters.q)
  if (filters.category) params.set('category', filters.category)
  if (filters.language) params.set('language', filters.language)
  if (filters.potentialMin) params.set('potential_min', filters.potentialMin)
  try { result.value = await api.projects(params) } catch (reason) { error.value = reason instanceof Error ? reason.message : '加载失败' } finally { loading.value = false }
}

onMounted(() => {
  load()
  loadWatchlist()
})
</script>

<template>
  <AppShell>
    <header class="hero compact hero-discover">
      <div>
        <p class="eyebrow">
          发现项目
        </p><h1>发现智能体项目</h1><p>按真实代码仓库元数据和确定性趋势评分筛选。</p>
      </div>
    </header>
    <form
      class="filter-bar"
      @submit.prevent="load(1)"
    >
      <label><span>搜索</span><input
        v-model="filters.q"
        placeholder="所有者/代码仓库"
      ></label>
      <label><span>分类</span><select v-model="filters.category"><option value="">全部分类</option><option value="AGENT_FRAMEWORK">智能体框架</option><option value="CODING_AGENT">编程智能体</option><option value="BROWSER_AGENT">浏览器智能体</option><option value="RESEARCH_AGENT">研究智能体</option><option value="MULTI_AGENT">多智能体</option><option value="MCP_TOOL">模型上下文协议工具</option><option value="OTHER_AGENT">其他智能体</option></select></label>
      <label><span>语言</span><input
        v-model="filters.language"
        placeholder="例如：Python"
      ></label>
      <label><span>最低潜力评分</span><input
        v-model="filters.potentialMin"
        type="number"
        min="0"
        max="100"
        placeholder="0～100"
      ></label>
      <label><span>排序</span><select v-model="filters.sort"><option value="-trend">趋势评分最高（仅数据充足）</option><option value="-potential">潜力评分最高（仅数据充足）</option><option value="-learning">学习价值最高（仅数据充足）</option><option value="-enterprise">企业成熟度最高（仅数据充足）</option><option value="-stars">星标数最高</option><option value="-updated">最近更新</option></select></label>
      <button
        class="button primary"
        type="submit"
      >
        应用筛选
      </button>
    </form>
    <section class="panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">
            项目索引
          </p><h2>{{ result?.count ?? 0 }} 个项目</h2>
        </div>
      </div>
      <div
        v-if="loading"
        class="loading-state"
      >
        正在筛选…
      </div><div
        v-else-if="error"
        class="error-state"
      >
        {{ error }}
      </div><ProjectTable
        v-else
        :projects="result?.results ?? []"
        :watched-ids="watchedIds"
        :watchlist-ready="watchlistReady"
        show-watch-status
      />
      <div
        v-if="result"
        class="pagination"
      >
        <button
          :disabled="!result.previous"
          @click="load(page - 1)"
        >
          上一页
        </button><span>第 {{ page }} 页</span><button
          :disabled="!result.next"
          @click="load(page + 1)"
        >
          下一页
        </button>
      </div>
    </section>
  </AppShell>
</template>
