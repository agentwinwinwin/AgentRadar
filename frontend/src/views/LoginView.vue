<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { setAuthSession } from '@/auth/session'

const route = useRoute()
const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const passwordConfirm = ref('')
const error = ref('')
const loading = ref(false)
const isRegister = computed(() => mode.value === 'register')

function switchMode(nextMode: 'login' | 'register') {
  mode.value = nextMode
  error.value = ''
  password.value = ''
  passwordConfirm.value = ''
}

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const result = isRegister.value
      ? await api.register(username.value, password.value, passwordConfirm.value)
      : await api.login(username.value, password.value)
    setAuthSession(result.token, result.user, result.expires_at)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.replace(redirect)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '操作失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-shell">
      <aside class="auth-intro">
        <div class="auth-glow auth-glow-one" />
        <div class="auth-glow auth-glow-two" />
        <RouterLink
          class="auth-brand"
          to="/dashboard"
        >
          <span class="auth-brand-mark">AR</span>
          <span><strong>AgentRadar</strong><small>开源智能体趋势洞察</small></span>
        </RouterLink>
        <div class="auth-copy">
          <p class="auth-kicker">
            从真实数据出发
          </p>
          <h1>发现值得持续关注的 AI Agent 项目</h1>
          <p>把 GitHub 活跃度、趋势评分和可追溯证据汇聚到一个清晰的决策工作台。</p>
        </div>
        <ul class="auth-benefits">
          <li><span>01</span>建立你的项目关注列表</li>
          <li><span>02</span>接收确定性变化提醒</li>
          <li><span>03</span>使用 PM Copilot 深入分析</li>
        </ul>
      </aside>

      <div class="auth-form-side">
        <form
          class="auth-card"
          @submit.prevent="submit"
        >
          <header class="auth-heading">
            <p class="eyebrow">
              {{ isRegister ? '创建账户' : '欢迎回来' }}
            </p>
            <h2>{{ isRegister ? '开始使用 AgentRadar' : '登录你的账户' }}</h2>
            <p>{{ isRegister ? '注册后即可保存关注、提醒和个人报告。' : '继续查看你的关注项目与最新动态。' }}</p>
          </header>

          <div
            class="auth-tabs"
            role="tablist"
            aria-label="账户操作"
          >
            <button
              type="button"
              :class="{ active: !isRegister }"
              @click="switchMode('login')"
            >
              登录
            </button>
            <button
              type="button"
              :class="{ active: isRegister }"
              @click="switchMode('register')"
            >
              注册
            </button>
          </div>

          <label class="auth-field">
            <span>用户名</span>
            <input
              v-model.trim="username"
              autocomplete="username"
              required
              minlength="3"
              maxlength="150"
              placeholder="请输入用户名"
            >
          </label>
          <label class="auth-field">
            <span>密码</span>
            <input
              v-model="password"
              type="password"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              required
              minlength="8"
              placeholder="至少 8 位密码"
            >
          </label>
          <label
            v-if="isRegister"
            class="auth-field"
          >
            <span>确认密码</span>
            <input
              v-model="passwordConfirm"
              type="password"
              autocomplete="new-password"
              required
              minlength="8"
              placeholder="再次输入密码"
            >
          </label>

          <p
            v-if="error"
            class="auth-error"
            role="alert"
          >
            {{ error }}
          </p>
          <button
            class="auth-submit"
            type="submit"
            :disabled="loading"
          >
            <span>{{ loading ? '处理中…' : isRegister ? '创建账户并进入' : '登录' }}</span>
            <span aria-hidden="true">→</span>
          </button>
          <p class="auth-footnote">
            账户仅用于隔离你的关注、提醒、报告与智能分析会话。
          </p>
        </form>
      </div>
    </section>
  </main>
</template>
