<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import type { AdminControlCenterData, AdminModelData } from '@/types/api'

const data = ref<AdminControlCenterData | null>(null)
const loading = ref(true)
const error = ref('')
const activating = ref(false)
const selectedModel = ref<AdminModelData | null>(null)
const confirmation = ref('')
const resultMessage = ref('')
const trainingConfirmation = ref('')
const trainingBusy = ref(false)
let trainingTimer: number | null = null

const capabilityLabels: Record<string, string> = {
  STAR_GROWTH_7D: '星标 7 天增长', STAR_GROWTH_30D: '星标 30 天增长',
  FORK_GROWTH_7D: '复刻 7 天增长', FORK_GROWTH_30D: '复刻 30 天增长',
  MOMENTUM: '增长动量', HYPE_RISK: '炒作风险', CATEGORY_TREND: '分类趋势',
  TREND_CHANGE_ALERT: '趋势变化提醒', POTENTIAL_CHANGE_ALERT: '潜力变化提醒',
  FORECAST_V2_DATA_READINESS: '预测 V2 数据成熟度',
}
const statusLabels: Record<string, string> = {
  READY: '已就绪', NOT_READY: '尚未就绪', DEGRADED: '降级运行', DISABLED: '已禁用',
  ACCUMULATING: '数据积累中', DATA_READY: '数据已就绪', TRAINED: '已训练',
  VALIDATED: '已验证', ACTIVE: '生产使用中', RETIRED: '已退役', QUEUED: '排队中',
  RUNNING: '训练中', COMPLETED: '已完成', FAILED: '失败', BLOCKED: '条件未满足',
  PASS: '通过', FAIL: '未通过', ok: '正常', failed: '异常',
}
const algorithmLabels: Record<string, string> = {
  logistic_regression: '逻辑回归', random_forest: '随机森林', xgboost: 'XGBoost',
  random_forest_regressor: '随机森林回归',
}
const featureLabels: Record<string, string> = {
  repo_age_days: '项目年龄（天）', category: '项目分类', age_cohort: '项目年龄分组',
  commit_7d: '近 7 天提交数', commit_30d: '近 30 天提交数',
  pr_created_7d: '近 7 天新建合并请求', pr_created_30d: '近 30 天新建合并请求',
  pr_merged_30d: '近 30 天已合并请求', issue_created_30d: '近 30 天新建议题',
  issue_closed_30d: '近 30 天已关闭议题', active_contributors_30d: '近 30 天活跃贡献者',
  release_count_30d: '近 30 天发布次数', days_since_last_release: '距上次发布天数',
  current_stars: '当前星标数', current_forks: '当前复刻数',
  days_since_last_push: '距上次推送天数', community_health: '社区健康度',
  topic_momentum: '主题动量',
}

const readyCapabilities = computed(
  () => data.value?.capabilities.filter((item) => item.status === 'READY').length ?? 0,
)
const forecastDefinition = computed(
  () => data.value?.product.forecast_definition.replace('Category', '分类') ?? '',
)
const starReadiness = computed(
  () => data.value?.capabilities.find((item) => item.name === 'FORECAST_V2_DATA_READINESS') ?? null,
)
const isStarRetrainingCycle = computed(
  () => starReadiness.value?.metrics.readiness_phase === 'NEXT_RETRAINING',
)

function maturityMetric(key: string): number {
  const fallbackKey = key === 'observed_target_span_repositories' ? 'observed_60d_repositories' : key
  const value = starReadiness.value?.metrics[key] ?? starReadiness.value?.metrics[fallbackKey]
  return typeof value === 'number' ? value : 0
}

function maturityPercent(actualKey: string, requiredKey: string): number {
  const required = maturityMetric(requiredKey)
  return required ? Math.min(100, (maturityMetric(actualKey) / required) * 100) : 0
}

function earliestReadyLabel(): string {
  const value = starReadiness.value?.metrics.earliest_label_ready_at
  return typeof value === 'string' ? new Date(value).toLocaleDateString('zh-CN') : '尚无法估算'
}

function numberMetric(metrics: Record<string, unknown>, key: string): string {
  const value = metrics[key]
  return typeof value === 'number' ? value.toFixed(3) : '—'
}

function topFeatures(model: AdminModelData): Array<[string, number]> {
  return Object.entries(model.feature_importance)
    .filter((entry): entry is [string, number] => typeof entry[1] === 'number')
    .sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]))
    .slice(0, 8)
}

function statusLabel(value: string): string { return statusLabels[value] ?? value }
function capabilityLabel(value: string): string { return capabilityLabels[value] ?? value }
function splitLabel(value: string | number): string {
  return ({ training: '训练集', validation: '验证集', test: '测试集' } as Record<string, string>)[String(value)] ?? String(value)
}
function featureLabel(value: string): string {
  const normalized = value.replace(/^(numeric|categorical)__/, '')
  const direct = featureLabels[normalized]
  if (direct) return direct
  const source = Object.keys(featureLabels).find((key) => normalized === key || normalized.startsWith(`${key}_`))
  return source ? `${featureLabels[source]} · ${normalized.slice(source.length + 1)}` : normalized
}

function blockerLabel(value: string): string {
  return value
    .replace('Validation', '验证集').replace('Test', '测试集')
    .replace('precision', '精确率').replace('recall', '召回率')
    .replace('Dataset Quality Gate', '数据质量门禁')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.adminControlCenter()
    scheduleTrainingPoll()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '管理数据读取失败'
  } finally {
    loading.value = false
  }
}

function scheduleTrainingPoll() {
  if (trainingTimer) window.clearTimeout(trainingTimer)
  const active = data.value?.training.runs.find((run) => ['QUEUED', 'RUNNING'].includes(run.status))
  if (active) trainingTimer = window.setTimeout(load, 5000)
}

async function checkTraining() {
  trainingBusy.value = true
  try {
    await api.checkAdminTraining()
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '训练条件检查失败'
  } finally {
    trainingBusy.value = false
  }
}

async function startTraining() {
  if (!data.value || trainingConfirmation.value !== data.value.training.readiness.confirmation_text) return
  trainingBusy.value = true
  error.value = ''
  try {
    await api.startAdminTraining(trainingConfirmation.value)
    trainingConfirmation.value = ''
    resultMessage.value = '训练任务已进入独立 ML 队列；完成后模型最多为 VALIDATED，不会自动上线。'
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '训练任务启动失败'
  } finally {
    trainingBusy.value = false
  }
}

function openActivation(model: AdminModelData) {
  selectedModel.value = model
  confirmation.value = ''
  resultMessage.value = ''
}

function closeActivation() {
  if (activating.value) return
  selectedModel.value = null
  confirmation.value = ''
}

async function activate() {
  if (!selectedModel.value || confirmation.value !== selectedModel.value.model_version) return
  activating.value = true
  error.value = ''
  try {
    const result = await api.activateAdminModel(
      selectedModel.value.model_version,
      confirmation.value,
    )
    resultMessage.value = `${result.model_version} 已由 ${result.activated_by} 激活。`
    selectedModel.value = null
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模型激活失败'
  } finally {
    activating.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => { if (trainingTimer) window.clearTimeout(trainingTimer) })
</script>

<template>
  <AppShell>
    <section class="admin-hero">
      <div>
        <p class="eyebrow">
          仅管理员可见
        </p>
        <h1>生产决策控制台</h1>
        <p>查看数据成熟度、模型验证证据和需要人工确认的生产操作。系统永远不会自动激活模型。</p>
      </div>
      <button
        class="button"
        :disabled="loading"
        @click="load"
      >
        刷新状态
      </button>
    </section>

    <div
      v-if="loading"
      class="loading-state"
    >
      正在读取生产状态…
    </div>
    <div
      v-else-if="error && !data"
      class="error-state"
    >
      {{ error }}
    </div>

    <template v-if="data">
      <section class="admin-summary-grid">
        <article>
          <span>系统状态</span>
          <strong :class="data.status === 'READY' ? 'status-good' : 'status-warn'">{{ statusLabel(data.status) }}</strong>
          <small>{{ new Date(data.checked_at).toLocaleString('zh-CN') }}</small>
        </article>
        <article>
          <span>已成熟能力</span>
          <strong>{{ readyCapabilities }} / {{ data.capabilities.length }}</strong>
          <small>只由真实数据覆盖决定</small>
        </article>
        <article>
          <span>趋势预测状态</span>
          <strong>{{ statusLabel(data.product.forecast_status) }}</strong>
          <small>{{ data.product.active_model_version ?? '尚无生产模型' }}</small>
        </article>
        <article>
          <span>候选模型</span>
          <strong>{{ data.product.validated_model_count }}</strong>
          <small>已验证不等于已上线</small>
        </article>
      </section>

      <p
        v-if="error"
        class="admin-inline-error"
      >
        {{ error }}
      </p>
      <p
        v-if="resultMessage"
        class="admin-success"
      >
        {{ resultMessage }}
      </p>

      <section class="admin-layout">
        <aside class="admin-rail">
          <h2>上线原则</h2>
          <p>{{ forecastDefinition }}</p>
          <dl>
            <div><dt>自动激活</dt><dd>已禁用</dd></div>
            <div
              v-for="(dependency, name) in data.dependencies"
              :key="name"
            >
              <dt>{{ name === 'postgresql' ? '数据库' : name === 'redis' ? '任务缓存' : name === 'configuration' ? '系统配置' : name }}</dt><dd>{{ statusLabel(dependency.status) }}</dd>
            </div>
          </dl>
          <div class="admin-warning">
            激活会让此前生产模型退役，并允许系统生成趋势预测。必须先阅读验证集、独立测试集和数据门禁。
          </div>
        </aside>

        <div class="admin-main">
          <section class="admin-section maturity-progress-panel">
            <header>
              <div>
                <p class="eyebrow">
                  真实数据积攒
                </p>
                <h2>{{ isStarRetrainingCycle ? '下一次 Star 增强模型再训练进度' : 'Star 增强模型首次上线进度' }}</h2>
              </div>
              <strong>{{ statusLabel(starReadiness?.status ?? 'ACCUMULATING') }}</strong>
            </header>
            <p>这里只计算系统持续采集的真实快照，不使用回填或伪造的历史 Star。模型上线后采集不会停止，但已发布的项目预测会固定到该模型版本，只有下一版模型人工激活时才批量更新。</p>
            <div class="maturity-stage-list">
              <article>
                <div><strong>真实快照跨度</strong><span>{{ maturityMetric('maximum_observed_span_days') }} / {{ maturityMetric('required_observed_span_days') }} 天</span></div>
                <progress
                  :value="maturityPercent('maximum_observed_span_days', 'required_observed_span_days')"
                  max="100"
                />
              </article>
              <article>
                <div><strong>具有目标跨度历史的项目</strong><span>{{ maturityMetric('observed_target_span_repositories') }} / {{ maturityMetric('required_observed_repositories') }}</span></div>
                <progress
                  :value="maturityPercent('observed_target_span_repositories', 'required_observed_repositories')"
                  max="100"
                />
              </article>
              <article>
                <div><strong>Star增强训练样本</strong><span>{{ maturityMetric('star_enhanced_training_samples') }} / {{ maturityMetric('required_training_samples') }}</span></div>
                <progress
                  :value="maturityPercent('star_enhanced_training_samples', 'required_training_samples')"
                  max="100"
                />
              </article>
              <article>
                <div><strong>有效项目分类</strong><span>{{ maturityMetric('qualified_categories') }} / {{ maturityMetric('required_categories') }}</span></div>
                <progress
                  :value="maturityPercent('qualified_categories', 'required_categories')"
                  max="100"
                />
              </article>
            </div>
            <div class="maturity-ready-note">
              <span>首批标签最早预计：{{ earliestReadyLabel() }}</span>
              <span>特征版本：feature-v2.0.0 · 标签版本：label-v2.0.0</span>
            </div>
            <button
              class="button primary"
              disabled
            >
              {{ isStarRetrainingCycle ? '下一轮数据成熟后可重新训练' : '数据成熟后开放 Star 增强模型训练' }}
            </button>
            <p class="admin-warning">
              进度就绪只允许管理员发起训练，不会自动训练或上线。人工激活新版本后才会重新预测全部具备可靠特征的项目；缺失输入的项目保持数据不足，不会伪造分数。
            </p>
          </section>

          <section class="admin-section training-panel">
            <header>
              <div>
                <p class="eyebrow">
                  模型训练
                </p><h2>开发活跃度模型训练（不含历史 Star）</h2>
              </div>
              <button
                class="button"
                :disabled="trainingBusy"
                @click="checkTraining"
              >
                重新检查训练条件
              </button>
            </header>
            <div class="model-metrics-grid">
              <div><span>数据质量门禁</span><strong>{{ data.training.readiness.quality_gate_passed ? '通过' : '未通过' }}</strong></div>
              <div><span>时间切分</span><strong>{{ data.training.readiness.time_split_ready ? '通过' : '未通过' }}</strong></div>
              <div><span>特征版本</span><strong>{{ data.training.readiness.feature_version }}</strong></div>
              <div><span>标签版本</span><strong>{{ data.training.readiness.label_version }}</strong></div>
            </div>
            <div class="training-splits">
              <span
                v-for="(split, name) in data.training.readiness.split_counts"
                :key="name"
              >
                {{ splitLabel(name) }}：{{ split.samples }}（正样本 {{ split.positive }} / 负样本 {{ split.negative }}）
              </span>
            </div>
            <div
              v-if="data.training.runs.length"
              class="training-run-list"
            >
              <article
                v-for="run in data.training.runs.slice(0, 3)"
                :key="run.id"
              >
                <strong>#{{ run.id }} · {{ statusLabel(run.status) }}</strong>
                <span>{{ run.requested_by }} · {{ new Date(run.requested_at).toLocaleString('zh-CN') }}</span>
                <p v-if="run.error_message">
                  {{ run.error_message }}
                </p>
                <p v-else-if="run.result.selected_model_version">
                  候选：{{ run.result.selected_model_version }}
                </p>
              </article>
            </div>
            <label class="training-confirmation">
              输入确认文本后启动：<code>{{ data.training.readiness.confirmation_text }}</code>
              <input
                v-model="trainingConfirmation"
                autocomplete="off"
                :placeholder="data.training.readiness.confirmation_text"
              >
            </label>
            <button
              class="button primary"
              :disabled="trainingBusy || !data.training.readiness.can_start || trainingConfirmation !== data.training.readiness.confirmation_text"
              @click="startTraining"
            >
              {{ trainingBusy ? '处理中…' : '启动模型训练' }}
            </button>
            <p class="admin-warning">
              训练使用真实数据集和按时间切分，运行于独立机器学习任务进程。完成后仅登记为“已验证”，仍需人工审核与激活。
            </p>
          </section>

          <section class="admin-section">
            <header>
              <div>
                <p class="eyebrow">
                  数据成熟度
                </p><h2>能力成熟度</h2>
              </div>
            </header>
            <div class="capability-list">
              <article
                v-for="capability in data.capabilities"
                :key="capability.name"
              >
                <div>
                  <strong>{{ capabilityLabel(capability.name) }}</strong>
                  <span :class="`capability-${capability.status.toLowerCase()}`">{{ statusLabel(capability.status) }}</span>
                </div>
                <progress
                  :value="capability.coverage"
                  max="1"
                />
                <p>{{ capability.reason || '暂无补充说明' }}</p>
                <small>覆盖率 {{ (capability.coverage * 100).toFixed(1) }}% · {{ capability.algorithm_version ?? '尚无算法版本' }}</small>
              </article>
            </div>
          </section>

          <section class="admin-section">
            <header>
              <div>
                <p class="eyebrow">
                  模型注册表
                </p><h2>模型候选与人工激活</h2>
              </div>
            </header>
            <div
              v-if="!data.models.length"
              class="empty-state"
            >
              模型注册表暂无记录。
            </div>
            <article
              v-for="model in data.models"
              :key="model.id"
              class="model-review-card"
            >
              <header>
                <div><span>{{ algorithmLabels[model.algorithm] ?? model.algorithm }}</span><h3>{{ model.model_version }}</h3><p>特征 {{ model.feature_version }} · 标签 {{ model.label_version }}</p></div>
                <strong :class="`model-status status-${model.status.toLowerCase()}`">{{ statusLabel(model.status) }}</strong>
              </header>
              <div class="model-metrics-grid">
                <div><span>验证集 PR-AUC</span><strong>{{ numberMetric(model.validation_metrics, 'pr_auc') }}</strong></div>
                <div><span>验证集 F1</span><strong>{{ numberMetric(model.validation_metrics, 'f1') }}</strong></div>
                <div><span>测试集 PR-AUC</span><strong>{{ numberMetric(model.test_metrics, 'pr_auc') }}</strong></div>
                <div><span>测试集 F1</span><strong>{{ numberMetric(model.test_metrics, 'f1') }}</strong></div>
              </div>
              <div
                class="model-gate"
                :class="{ passed: model.activation_eligible }"
              >
                <strong>{{ model.activation_eligible ? '激活门禁已通过' : '暂不可激活' }}</strong>
                <ul v-if="model.activation_blockers.length">
                  <li
                    v-for="blocker in model.activation_blockers"
                    :key="blocker"
                  >
                    {{ blockerLabel(blocker) }}
                  </li>
                </ul>
                <p v-else>
                  数据集、验证集和独立测试集已达到当前最低生产门槛，仍需管理员判断指标是否足够可信。
                </p>
              </div>
              <details>
                <summary>查看主要特征重要性与模型文件校验</summary>
                <ul class="feature-list">
                  <li
                    v-for="feature in topFeatures(model)"
                    :key="feature[0]"
                  >
                    <span>{{ featureLabel(feature[0]) }}</span><strong>{{ feature[1].toFixed(4) }}</strong>
                  </li>
                </ul>
                <code>SHA-256 {{ model.artifact_sha256 }}</code>
              </details>
              <footer>
                <span>训练期 {{ new Date(model.training_start).toLocaleDateString('zh-CN') }} — {{ new Date(model.training_end).toLocaleDateString('zh-CN') }}</span>
                <button
                  v-if="model.status === 'VALIDATED'"
                  class="button primary"
                  :disabled="!model.activation_eligible"
                  @click="openActivation(model)"
                >
                  审核并激活
                </button>
              </footer>
            </article>
          </section>
        </div>
      </section>
    </template>

    <div
      v-if="selectedModel"
      class="admin-dialog-backdrop"
      @click.self="closeActivation"
    >
      <section
        class="admin-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="activation-title"
      >
        <p class="eyebrow">
          高风险生产操作
        </p>
        <h2 id="activation-title">
          确认激活趋势预测模型
        </h2>
        <p>请再次核对指标。激活后，系统将允许该模型产生“{{ forecastDefinition }}”。</p>
        <label>
          输入完整模型版本确认
          <code>{{ selectedModel.model_version }}</code>
          <input
            v-model="confirmation"
            autocomplete="off"
            :placeholder="selectedModel.model_version"
          >
        </label>
        <div class="admin-dialog-actions">
          <button
            class="button"
            :disabled="activating"
            @click="closeActivation"
          >
            取消
          </button>
          <button
            class="button danger"
            :disabled="activating || confirmation !== selectedModel.model_version"
            @click="activate"
          >
            {{ activating ? '正在激活…' : '确认激活生产模型' }}
          </button>
        </div>
      </section>
    </div>
  </AppShell>
</template>
