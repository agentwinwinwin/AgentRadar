import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "apps.accounts",
    "apps.common",
    "apps.github",
    "apps.repositories",
    "apps.snapshots",
    "apps.activities",
    "apps.trends",
    "apps.potentials",
    "apps.datasets",
    "apps.forecasts",
    "apps.knowledge",
    "apps.learning",
    "apps.enterprise",
    "apps.tools",
    "apps.skills",
    "apps.agent",
    "apps.watchlists",
    "apps.operations",
    "apps.interactions",
    "apps.capabilities",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.ExpiringTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("API_ANON_RATE", "120/min"),
        "user": os.getenv("API_USER_RATE", "600/min"),
        "agent": os.getenv("AGENT_REQUEST_RATE", "20/min"),
        "auth": os.getenv("AUTH_RATE", "10/min"),
    },
}

AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(3 * 60 * 60)))

DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("REQUEST_MAX_BYTES", "1048576"))
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.common.logging.StructuredJsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "loggers": {
        "agentradar": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_EXPIRES = int(os.getenv("CELERY_RESULT_EXPIRES", "86400"))
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "evaluate-data-maturity-daily": {
        "task": "capabilities.evaluate_data_maturity",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "operations"},
    },
    "enforce-data-retention-daily": {
        "task": "operations.enforce_data_retention",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "operations"},
    },
    "dispatch-due-snapshots-hourly": {
        "task": "snapshots.dispatch_due_snapshots",
        "schedule": 60 * 60,
        "options": {"queue": "github_normal"},
    },
    "reassess-monitoring-tiers-daily": {
        "task": "snapshots.reassess_monitoring_tiers",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "operations"},
    },
    "discover-new-repositories-every-6-hours": {
        "task": "repositories.discover_new_repositories",
        "schedule": 6 * 60 * 60,
        "options": {"queue": "github_normal"},
    },
    "refresh-recent-repositories-daily": {
        "task": "repositories.refresh_recent_repositories",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "github_normal"},
    },
    "dispatch-due-repository-activity-hourly": {
        "task": "activities.capture_daily_activity_metrics",
        "schedule": 60 * 60,
        "options": {"queue": "github_normal"},
    },
    "dispatch-knowledge-sync-daily": {
        "task": "knowledge.dispatch_knowledge_sync",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "knowledge"},
    },
    "dispatch-assessment-enrichment-daily": {
        "task": "learning.dispatch_assessment_enrichment",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "github_normal"},
    },
    "dispatch-alert-evaluation-daily": {
        "task": "alerts.dispatch_alert_evaluation",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "scoring"},
    },
    "generate-daily-report": {
        "task": "reports.generate_daily_report",
        "schedule": 24 * 60 * 60,
        "options": {"queue": "scoring"},
    },
    "generate-weekly-report": {
        "task": "reports.generate_weekly_report",
        "schedule": 7 * 24 * 60 * 60,
        "options": {"queue": "scoring"},
    },
}
CELERY_TASK_ROUTES = {
    "repositories.localize_repository": {"queue": "interactive"},
    "learning.enrich_repository_score_evidence": {"queue": "github_normal"},
    "learning.dispatch_assessment_enrichment": {"queue": "github_normal"},
    "repositories.*": {"queue": "github_normal"},
    "snapshots.*": {"queue": "github_normal"},
    "activities.*": {"queue": "github_normal"},
    "trends.*": {"queue": "scoring"},
    "potentials.*": {"queue": "scoring"},
    "datasets.*": {"queue": "github_backfill"},
    "forecasts.*": {"queue": "ml"},
    "knowledge.*": {"queue": "knowledge"},
    "learning.*": {"queue": "scoring"},
    "enterprise.*": {"queue": "scoring"},
    "alerts.*": {"queue": "scoring"},
    "reports.*": {"queue": "scoring"},
    "operations.*": {"queue": "operations"},
    "capabilities.*": {"queue": "operations"},
}

REPOSITORY_TASK_COALESCE_TTL_SECONDS = int(
    os.getenv("REPOSITORY_TASK_COALESCE_TTL_SECONDS", "900")
)
ALERT_FULL_SCAN_BACKLOG_THRESHOLD = int(os.getenv("ALERT_FULL_SCAN_BACKLOG_THRESHOLD", "1000"))
ALERT_FULL_SCAN_COALESCE_TTL_SECONDS = int(
    os.getenv("ALERT_FULL_SCAN_COALESCE_TTL_SECONDS", str(23 * 60 * 60))
)

ALERT_RETENTION_DAYS = int(os.getenv("ALERT_RETENTION_DAYS", "365"))
REPORT_RETENTION_DAYS = int(os.getenv("REPORT_RETENTION_DAYS", "365"))
WATCHLIST_EVENT_RETENTION_DAYS = int(os.getenv("WATCHLIST_EVENT_RETENTION_DAYS", "730"))

CAPABILITY_MIN_REPOSITORIES = int(os.getenv("CAPABILITY_MIN_REPOSITORIES", "20"))
CAPABILITY_MIN_COVERAGE = float(os.getenv("CAPABILITY_MIN_COVERAGE", "0.50"))
CATEGORY_TREND_MIN_REPOSITORIES = int(os.getenv("CATEGORY_TREND_MIN_REPOSITORIES", "20"))
CATEGORY_TREND_MIN_COVERAGE = float(os.getenv("CATEGORY_TREND_MIN_COVERAGE", "0.60"))
CATEGORY_TREND_MIN_CATEGORIES = int(os.getenv("CATEGORY_TREND_MIN_CATEGORIES", "2"))
FORECAST_V2_MIN_REPOSITORIES = int(os.getenv("FORECAST_V2_MIN_REPOSITORIES", "200"))
FORECAST_V2_MIN_TRAINING_SAMPLES = int(os.getenv("FORECAST_V2_MIN_TRAINING_SAMPLES", "200"))
FORECAST_V2_MIN_CATEGORIES = int(os.getenv("FORECAST_V2_MIN_CATEGORIES", "3"))
CAPABILITY_RECALC_BATCH_SIZE = int(os.getenv("CAPABILITY_RECALC_BATCH_SIZE", "200"))
ASSESSMENT_SCORING_BATCH_SIZE = int(os.getenv("ASSESSMENT_SCORING_BATCH_SIZE", "100"))
ASSESSMENT_ENRICHMENT_BATCH_SIZE = int(os.getenv("ASSESSMENT_ENRICHMENT_BATCH_SIZE", "25"))

LEARNING_RANKING_MIN_CONFIDENCE = float(os.getenv("LEARNING_RANKING_MIN_CONFIDENCE", "0.60"))
ENTERPRISE_RANKING_MIN_CONFIDENCE = float(os.getenv("ENTERPRISE_RANKING_MIN_CONFIDENCE", "0.60"))
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_TOOL_TIMEOUT_SECONDS = int(os.getenv("MCP_TOOL_TIMEOUT_SECONDS", "10"))
_skill_root = Path(os.getenv("SKILL_ROOT", "skills"))
SKILL_ROOT = _skill_root if _skill_root.is_absolute() else BASE_DIR.parent / _skill_root

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.6-sol")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = (
    os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY", "")
)
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "6000"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
AGENT_SESSION_TTL_SECONDS = int(os.getenv("AGENT_SESSION_TTL_SECONDS", "86400"))
AGENT_SESSION_MAX_TURNS = int(os.getenv("AGENT_SESSION_MAX_TURNS", "8"))
AGENT_MAX_CONTEXT_CHARS = int(os.getenv("AGENT_MAX_CONTEXT_CHARS", "24000"))
AGENT_MAX_EVIDENCE = int(os.getenv("AGENT_MAX_EVIDENCE", "20"))
AGENT_MAX_TOTAL_TOKENS = int(os.getenv("AGENT_MAX_TOTAL_TOKENS", "16000"))

ML_ARTIFACT_ROOT = BASE_DIR.parent / "ml" / "artifacts"

REPOSITORY_SNAPSHOT_BUCKET_HOURS = 6
REPOSITORY_SYNC_LOCK_TTL_SECONDS = 300
REPOSITORY_SYNC_LOCK_RETRY_SECONDS = 10
MONITORING_TIER_INTERVAL_HOURS = {
    "HOT": 6,
    "NEW": 12,
    "RISING": 12,
    "NORMAL": 24,
    "STABLE": 72,
    "DORMANT": 168,
    "ARCHIVED": 24 * 30,
}
SNAPSHOT_DISPATCH_BATCH_SIZE = int(os.getenv("SNAPSHOT_DISPATCH_BATCH_SIZE", "225"))
MONITORING_MIN_OBSERVED_DAYS = int(os.getenv("MONITORING_MIN_OBSERVED_DAYS", "60"))
MONITORING_LOW_STAR_GROWTH_30D = int(os.getenv("MONITORING_LOW_STAR_GROWTH_30D", "10"))
MONITORING_LOW_FORK_GROWTH_30D = int(os.getenv("MONITORING_LOW_FORK_GROWTH_30D", "2"))
MONITORING_LOW_COMMITS_30D = int(os.getenv("MONITORING_LOW_COMMITS_30D", "10"))
MONITORING_LOW_PRS_30D = int(os.getenv("MONITORING_LOW_PRS_30D", "5"))
MONITORING_LOW_CONTRIBUTORS_30D = int(
    os.getenv("MONITORING_LOW_CONTRIBUTORS_30D", "2")
)
ACTIVITY_DISPATCH_BATCH_SIZE = int(os.getenv("ACTIVITY_DISPATCH_BATCH_SIZE", "50"))
ACTIVITY_SYNC_RATE_LIMIT = os.getenv("ACTIVITY_SYNC_RATE_LIMIT", "1/m")
ACTIVITY_TIER_INTERVAL_DAYS = {
    "HOT": 1,
    "NEW": 1,
    "RISING": 1,
    "NORMAL": 3,
    "STABLE": 7,
    "DORMANT": 30,
    "ARCHIVED": 90,
}
GITHUB_CORE_MIN_REMAINING = int(os.getenv("GITHUB_CORE_MIN_REMAINING", "100"))
GITHUB_SEARCH_MIN_REMAINING = int(os.getenv("GITHUB_SEARCH_MIN_REMAINING", "5"))
CONTINUOUS_DISCOVERY_PER_QUERY = int(os.getenv("CONTINUOUS_DISCOVERY_PER_QUERY", "20"))
CONTRIBUTOR_STATS_RETRY_SECONDS = 60
DATASET_MIN_LABEL_COHORT_SIZE = int(os.getenv("DATASET_MIN_LABEL_COHORT_SIZE", "20"))
KNOWLEDGE_EMBEDDING_PROVIDER = os.getenv("KNOWLEDGE_EMBEDDING_PROVIDER", "local_hashing")
KNOWLEDGE_EMBEDDING_MODEL = os.getenv("KNOWLEDGE_EMBEDDING_MODEL", "hashing-384")
KNOWLEDGE_EMBEDDING_VERSION = "embedding-v1.0.0"
KNOWLEDGE_EMBEDDING_DIMENSIONS = 384
KNOWLEDGE_SYNC_BATCH_SIZE = int(os.getenv("KNOWLEDGE_SYNC_BATCH_SIZE", "25"))
KNOWLEDGE_MAX_FILE_BYTES = int(os.getenv("KNOWLEDGE_MAX_FILE_BYTES", "500000"))
KNOWLEDGE_MAX_DOC_FILES = int(os.getenv("KNOWLEDGE_MAX_DOC_FILES", "25"))
KNOWLEDGE_TIER_INTERVAL_HOURS = {
    "HOT": 24,
    "RISING": 24,
    "NEW": 72,
    "NORMAL": 24 * 3,
    "STABLE": 24 * 7,
    "DORMANT": 24 * 30,
    "ARCHIVED": 24 * 90,
}

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")
GITHUB_API_VERSION = "2022-11-28"
