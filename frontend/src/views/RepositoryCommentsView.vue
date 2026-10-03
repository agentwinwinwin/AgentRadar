<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { isAuthenticated } from '@/auth/session'
import AppShell from '@/components/AppShell.vue'
import type { PaginatedRepositoryComments, ProjectDetail, RepositoryCommunity } from '@/types/api'

const route = useRoute()
const router = useRouter()
const repositoryId = Number(route.params.id)
const detail = ref<ProjectDetail | null>(null)
const community = ref<RepositoryCommunity | null>(null)
const comments = ref<PaginatedRepositoryComments | null>(null)
const page = ref(1)
const content = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')

async function loadComments(targetPage = page.value) {
  comments.value = await api.comments(repositoryId, targetPage)
  page.value = targetPage
}

async function load() {
  try {
    [detail.value, community.value, comments.value] = await Promise.all([
      api.project(repositoryId),
      api.community(repositoryId),
      api.comments(repositoryId),
    ])
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '评论加载失败'
  } finally {
    loading.value = false
  }
}

async function submitComment() {
  const value = content.value.trim()
  if (!value) return
  if (!isAuthenticated.value) {
    await router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  busy.value = true
  error.value = ''
  try {
    await api.comment(repositoryId, value)
    content.value = ''
    await Promise.all([loadComments(1), api.community(repositoryId).then((value) => { community.value = value })])
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '评论发布失败'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <div
      v-if="loading"
      class="loading-state"
    >
      正在读取项目讨论…
    </div>
    <div
      v-else-if="!detail || !community || !comments"
      class="error-state"
    >
      {{ error || '评论数据不可用' }}
    </div>
    <template v-else>
      <header class="comments-hero">
        <div>
          <RouterLink
            class="comments-back"
            :to="{ name: 'project-detail', params: { id: repositoryId } }"
          >
            ← 返回项目详情
          </RouterLink>
          <p class="eyebrow">
            公开项目讨论
          </p>
          <h1>{{ detail.full_name }}</h1>
          <p>共 {{ comments.count }} 条评论。这里的讨论对所有访问者公开，登录后可以发表观点。</p>
        </div>
        <div class="comments-stats">
          <span>社区互动</span>
          <strong>{{ community.like_count }}</strong>
          <small>点赞 · {{ comments.count }} 条评论</small>
        </div>
      </header>

      <section class="comments-layout">
        <aside class="panel comment-compose-panel">
          <p class="eyebrow">
            参与讨论
          </p>
          <h2>{{ isAuthenticated ? '分享你的项目判断' : '登录后发表评论' }}</h2>
          <p>可以讨论上手体验、架构设计、工程风险与应用建议。</p>
          <form
            class="comment-form"
            @submit.prevent="submitComment"
          >
            <textarea
              v-model="content"
              maxlength="2000"
              rows="6"
              :placeholder="isAuthenticated ? '写下你的观点…' : '登录后可以发表评论'"
              :disabled="!isAuthenticated || busy"
            />
            <div>
              <small>{{ content.length }}/2000</small>
              <button
                class="button primary"
                type="submit"
                :disabled="!content.trim() || busy"
              >
                {{ busy ? '发布中…' : '发布评论' }}
              </button>
            </div>
          </form>
          <button
            v-if="!isAuthenticated"
            class="button comment-login"
            type="button"
            @click="router.push({ name: 'login', query: { redirect: route.fullPath } })"
          >
            登录后参与讨论
          </button>
          <p
            v-if="error"
            class="error-state compact-error"
          >
            {{ error }}
          </p>
        </aside>

        <section class="panel comments-feed">
          <div class="section-heading">
            <div>
              <p class="eyebrow">
                全部评论
              </p><h2>大家正在讨论</h2>
            </div>
            <span class="comment-count-badge">{{ comments.count }} 条</span>
          </div>
          <div
            v-if="comments.results.length"
            class="comment-list"
          >
            <article
              v-for="comment in comments.results"
              :key="comment.id"
              class="comment-item"
            >
              <span class="comment-avatar">{{ comment.author.username.slice(0, 1).toUpperCase() }}</span>
              <div>
                <header><strong>{{ comment.author.username }}</strong><time>{{ new Date(comment.created_at).toLocaleString('zh-CN') }}</time></header>
                <p>{{ comment.content }}</p>
              </div>
            </article>
          </div>
          <div
            v-else
            class="empty-state comment-empty"
          >
            还没有评论，来分享第一个观点吧。
          </div>
          <div
            v-if="comments.previous || comments.next"
            class="pagination"
          >
            <button
              :disabled="!comments.previous"
              @click="loadComments(page - 1)"
            >
              上一页
            </button>
            <span>第 {{ page }} 页</span>
            <button
              :disabled="!comments.next"
              @click="loadComments(page + 1)"
            >
              下一页
            </button>
          </div>
        </section>
      </section>
    </template>
  </AppShell>
</template>
