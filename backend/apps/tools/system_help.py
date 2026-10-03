# ruff: noqa: E501

from __future__ import annotations

from typing import Any

HELP_TOPICS = (
    "GENERAL",
    "TREND_SCORE",
    "POTENTIAL_SCORE",
    "FORECAST",
    "DATA_COMPLETENESS",
    "HYPE_RISK",
    "MOMENTUM",
    "WATCHLIST",
    "ALERTS",
    "REPORTS",
    "MODEL_TRAINING",
    "DATA_COLLECTION",
    "COPILOT",
)


_HELP: dict[str, dict[str, Any]] = {
    "GENERAL": {
        "title": "AgentRadar 使用说明",
        "explanation": "AgentRadar用于发现、跟踪和分析GitHub上的AI Agent开源项目。数据看板查看整体信号，发现项目用于筛选，项目详情用于查看证据，分析助手用于组合系统已有数据。",
        "limitations": ["项目事实以数据库和工具证据为准", "数据不足时不会把NULL解释为0"],
    },
    "TREND_SCORE": {
        "title": "趋势评分",
        "explanation": "趋势评分是同Category与仓库年龄Cohort中的确定性相对评分，综合动量、开发、社区、交付、维护等可用分量。它不是机器学习概率，也不代表商业成功。",
        "limitations": ["历史不足会降低data_completeness", "相同算法版本和输入得到相同结果"],
    },
    "POTENTIAL_SCORE": {
        "title": "潜力评分",
        "explanation": "没有可用增强模型时，潜力评分复用趋势、动量、社区、交付和炒作风险等确定性信号；ACTIVE的Star增强百分位模型具备可靠输入时，页面可按既定契约显示模型预测百分位。",
        "limitations": ["确定性Potential不是Forecast概率", "模型输入不足时回退确定性评分"],
    },
    "FORECAST": {
        "title": "未来活跃增长预测",
        "explanation": "Forecast V1表示项目未来30天进入同Category高开发活跃增长组的概率，只能由通过训练、验证、独立测试并由管理员人工激活的模型产生。",
        "limitations": ["不是Star上涨或爆火概率", "没有ACTIVE模型时状态为NOT_READY"],
    },
    "DATA_COMPLETENESS": {
        "title": "数据完整度",
        "explanation": "数据完整度表示评分所需真实输入的覆盖程度。缺失字段保持NULL，并按可用分量重新归一化；完整度低的项目不会进入正式可靠排行榜。",
        "limitations": ["NULL不等于0", "完整度会随真实历史积累自动变化"],
    },
    "HYPE_RISK": {
        "title": "炒作风险",
        "explanation": "炒作风险用于比较Star/Fork增长与开发活动是否失衡。只有真实Observed快照和开发活动历史均达到门禁时才计算。",
        "limitations": ["历史不足时为UNKNOWN或ACCUMULATING", "数据不足不会错误扣分"],
    },
    "MOMENTUM": {
        "title": "动量",
        "explanation": "动量反映近期Star/Fork增长与开发活动变化。所需7日或30日Observed快照及活动覆盖满足门禁后自动进入READY，并触发评分重算。",
        "limitations": ["不能用BACKFILLED活动伪造历史Star/Fork", "未成熟时保持NULL"],
    },
    "WATCHLIST": {
        "title": "我的关注",
        "explanation": "登录后可以在发现项目或项目详情添加关注，在我的关注页面查看并取消。重复关注保持幂等，不改变Candidate、Tracked或Training Pool。",
        "limitations": ["分析助手只能读取关注列表", "添加和取消必须由用户明确操作"],
    },
    "ALERTS": {
        "title": "动态提醒",
        "explanation": "动态提醒由版本化确定性规则根据Snapshot、Trend、Potential、Release和Activity产生，并包含可追溯Evidence。",
        "limitations": ["LLM不决定是否触发", "历史不足时不产生虚假7日或30日提醒"],
    },
    "REPORTS": {
        "title": "定期报告",
        "explanation": "日报和周报汇总新项目、关注变化、趋势、潜力、版本和活跃度变化，事实来自结构化服务。",
        "limitations": ["LLM如参与仅组织语言", "报告不重新计算评分"],
    },
    "MODEL_TRAINING": {
        "title": "模型训练与激活",
        "explanation": "管理员先检查真实Dataset Quality Gate，再启动时间切分训练和Validation/Test。模型训练完成最多进入VALIDATED，必须人工确认完整model_version后才能ACTIVE。",
        "limitations": ["不会自动激活或替换生产模型", "指标未达门槛时保持不可激活"],
    },
    "DATA_COLLECTION": {
        "title": "数据采集",
        "explanation": "Celery Beat按监控层级派发Snapshot和Activity任务，GitHub访问统一经过GitHubClient。Redis锁、数据库唯一约束、Rate Limit和Retry共同保证稳定与幂等。",
        "limitations": ["页面访问不实时抓GitHub", "Star/Fork历史只来自Observed Snapshot"],
    },
    "COPILOT": {
        "title": "分析助手工作流",
        "explanation": "分析助手先识别意图，再选择版本化Skill，通过MCP只读Tool查询Service和数据库，最后由配置的LLM根据Evidence组织中文回答。",
        "limitations": ["LLM不计算权威评分", "项目知识未入库或工具失败时会明确证据不足"],
    },
}


def system_help(topic: str) -> dict[str, Any]:
    item = _HELP[topic]
    return {
        "topic": topic,
        **item,
        "evidence": {
            "source": "TRUSTED_BUILT_IN_DOCUMENTATION",
            "documentation_version": "system-help-v1.0.0",
        },
    }
