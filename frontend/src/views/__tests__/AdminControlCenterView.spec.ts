import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import AdminControlCenterView from '../AdminControlCenterView.vue'

vi.mock('@/api/client', () => ({
  api: {
    adminControlCenter: vi.fn(),
    activateAdminModel: vi.fn(),
    checkAdminTraining: vi.fn(),
    startAdminTraining: vi.fn(),
    adminTrainingRun: vi.fn(),
  },
}))

describe('AdminControlCenterView', () => {
  it('shows maturity evidence and requires exact activation confirmation', async () => {
    vi.mocked(api.adminControlCenter).mockResolvedValue({
      status: 'READY',
      checked_at: '2026-08-19T00:00:00Z',
      dependencies: { postgresql: { status: 'ok' }, redis: { status: 'ok' } },
      product: {
        forecast_status: 'NOT_READY',
        active_model_version: null,
        validated_model_count: 1,
        forecast_definition: '未来30天进入同 Category 高开发活跃增长组的概率',
        automatic_activation: false,
      },
      capabilities: [
        {
          name: 'STAR_GROWTH_7D', status: 'READY', coverage: 0.88,
          first_ready_at: '2026-08-18T00:00:00Z', last_evaluated_at: '2026-08-19T00:00:00Z',
          reason: '真实历史已满足', algorithm_version: 'growth-v1', metrics: {},
        },
        {
          name: 'FORECAST_V2_DATA_READINESS', status: 'ACCUMULATING', coverage: 0.1,
          first_ready_at: null, last_evaluated_at: '2026-08-19T00:00:00Z',
          reason: '仍在积累', algorithm_version: 'forecast-v2-readiness-v1.0.0',
          metrics: {
            maximum_observed_span_days: 10, required_observed_span_days: 60,
            observed_60d_repositories: 0, required_observed_repositories: 200,
            star_enhanced_training_samples: 0, required_training_samples: 200,
            qualified_categories: 0, required_categories: 3,
            earliest_label_ready_at: '2026-11-16T00:00:00Z',
          },
        },
      ],
      models: [{
        id: 1, model_name: 'activity-growth-30d', model_version: 'forecast-v1-test',
        feature_version: 'feature-v1', label_version: 'label-v1.2.0', algorithm: 'xgboost',
        status: 'VALIDATED', training_start: '2026-01-01T00:00:00Z', training_end: '2026-06-01T00:00:00Z',
        validation_metrics: { pr_auc: 0.5, f1: 0.6 }, test_metrics: { pr_auc: 0.45, f1: 0.55 },
        dataset_quality: { passed: true }, feature_importance: { commit_30d: 0.4 },
        artifact_sha256: 'a'.repeat(64), activation_eligible: true, activation_blockers: [],
        activated_at: null, prediction_rollout_status: 'NOT_STARTED',
        prediction_rollout: {}, retraining_targets: {},
        created_at: '2026-08-19T00:00:00Z',
      }],
      training: {
        readiness: {
          early_stop: true, quality_gate_passed: true, time_split_ready: true,
          can_start: true, blocking_run_id: null, feature_version: 'feature-v1',
          label_version: 'label-v1.2.0', confirmation_text: 'START TRAINING label-v1.2.0',
          evaluated_at: '2026-08-19T00:00:00Z',
          split_counts: { training: { samples: 180, positive: 25, negative: 155 } },
          checks: {}, quality: {},
        },
        runs: [],
      },
    })
    vi.mocked(api.activateAdminModel).mockResolvedValue({
      model_version: 'forecast-v1-test', status: 'ACTIVE', activated_by: 'operator',
    })

    const wrapper = mount(AdminControlCenterView, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('生产决策控制台')
    expect(wrapper.text()).toContain('星标 7 天增长')
    expect(wrapper.text()).toContain('近 30 天提交数')
    expect(wrapper.text()).toContain('Star 增强模型首次上线进度')
    expect(wrapper.text()).toContain('10 / 60 天')
    expect(wrapper.text()).toContain('开发活跃度模型训练（不含历史 Star）')
    expect(wrapper.text()).toContain('激活门禁已通过')
    await wrapper.get('.model-review-card .button.primary').trigger('click')
    const activationButton = wrapper.get('.admin-dialog .button.danger')
    expect(activationButton.attributes('disabled')).toBeDefined()
    await wrapper.get('.admin-dialog input').setValue('forecast-v1-test')
    await activationButton.trigger('click')
    await flushPromises()
    expect(api.activateAdminModel).toHaveBeenCalledWith('forecast-v1-test', 'forecast-v1-test')
  })
})
