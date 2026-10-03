import { createRouter, createWebHistory } from 'vue-router'

import { api } from '@/api/client'
import {
  authToken,
  clearAuthSession,
  isAuthenticated,
  updateAuthUser,
} from '@/auth/session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/discover', name: 'discover', component: () => import('@/views/DiscoverView.vue') },
    { path: '/projects/:id', name: 'project-detail', component: () => import('@/views/RepositoryDetailView.vue') },
    { path: '/projects/:id/comments', name: 'project-comments', component: () => import('@/views/RepositoryCommentsView.vue') },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    { path: '/copilot', name: 'copilot', component: () => import('@/views/CopilotView.vue'), meta: { requiresAuth: true } },
    { path: '/watchlist', name: 'watchlist', component: () => import('@/views/WatchlistView.vue'), meta: { requiresAuth: true } },
    { path: '/alerts', name: 'alerts', component: () => import('@/views/AlertsView.vue'), meta: { requiresAuth: true } },
    { path: '/reports', name: 'reports', component: () => import('@/views/ReportsView.vue'), meta: { requiresAuth: true } },
    { path: '/admin', name: 'admin-control-center', component: () => import('@/views/AdminControlCenterView.vue'), meta: { requiresAuth: true, requiresAdmin: true } },
  ],
})

window.addEventListener('agentradar:session-expired', () => {
  const current = router.currentRoute.value
  if (current.meta.requiresAuth) {
    void router.replace({ name: 'login', query: { redirect: current.fullPath } })
  }
})

router.beforeEach(async (to) => {
  if (to.name === 'login' && isAuthenticated.value) return { name: 'dashboard' }
  if (!to.meta.requiresAuth) return

  if (!authToken.value) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  try {
    const user = await api.me()
    updateAuthUser(user)
    if (to.meta.requiresAdmin && !user.is_staff) return { name: 'dashboard' }
  } catch {
    clearAuthSession()
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

export default router
