<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { authUser, clearAuthSession, isAuthenticated } from '@/auth/session'

const router = useRouter()
const currentPath = computed(
  () => router?.currentRoute?.value?.path ?? window.location.pathname,
)

async function logout() {
  try {
    await api.logout()
  } finally {
    clearAuthSession()
    await router.push('/login')
  }
}
</script>

<template>
  <div class="app-shell">
    <div class="app-ambient app-ambient-one" />
    <div class="app-ambient app-ambient-two" />
    <header class="topbar">
      <RouterLink
        class="brand"
        to="/dashboard"
      >
        <span class="brand-mark">AR</span>
        <span><strong>AgentRadar</strong><small>开源智能体趋势洞察</small></span>
      </RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/dashboard">
          <span aria-hidden="true">◫</span> 数据看板
        </RouterLink>
        <RouterLink
          to="/discover"
          :class="{ 'router-link-active': currentPath.startsWith('/projects/') }"
        >
          <span aria-hidden="true">⌕</span> 发现项目
        </RouterLink>
        <RouterLink
          v-if="isAuthenticated"
          to="/copilot"
        >
          <span aria-hidden="true">✦</span> 智能分析
        </RouterLink>
        <RouterLink
          v-if="isAuthenticated"
          to="/watchlist"
        >
          <span aria-hidden="true">♡</span> 我的关注
        </RouterLink>
        <RouterLink
          v-if="isAuthenticated"
          to="/alerts"
        >
          <span aria-hidden="true">◌</span> 动态提醒
        </RouterLink>
        <RouterLink
          v-if="isAuthenticated"
          to="/reports"
        >
          <span aria-hidden="true">▤</span> 定期报告
        </RouterLink>
        <RouterLink
          v-if="authUser?.is_staff"
          class="admin-nav-link"
          to="/admin"
        >
          <span aria-hidden="true">⚙</span> 管理控制台
        </RouterLink>
        <button
          v-if="isAuthenticated"
          class="account-button"
          type="button"
          :title="`退出 ${authUser?.username}`"
          @click="logout"
        >
          <span class="account-avatar">{{ authUser?.username.slice(0, 1).toUpperCase() }}</span>
          <span>{{ authUser?.username }}</span>
          <small>退出</small>
        </button>
        <RouterLink
          v-else
          to="/login"
        >
          登录
        </RouterLink>
      </nav>
    </header>
    <main class="page-wrap">
      <slot />
    </main>
  </div>
</template>
