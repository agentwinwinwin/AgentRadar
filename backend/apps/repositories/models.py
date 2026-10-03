from django.db import models


class RepositoryCategory(models.TextChoices):
    AGENT_FRAMEWORK = "AGENT_FRAMEWORK", "Agent framework"
    CODING_AGENT = "CODING_AGENT", "Coding agent"
    BROWSER_AGENT = "BROWSER_AGENT", "Browser agent"
    RESEARCH_AGENT = "RESEARCH_AGENT", "Research agent"
    MULTI_AGENT = "MULTI_AGENT", "Multi-agent"
    AGENT_MEMORY = "AGENT_MEMORY", "Agent memory"
    AGENT_WORKFLOW = "AGENT_WORKFLOW", "Agent workflow"
    MCP_TOOL = "MCP_TOOL", "MCP tool"
    COMPUTER_USE = "COMPUTER_USE", "Computer use"
    AGENT_OBSERVABILITY = "AGENT_OBSERVABILITY", "Agent observability"
    AGENT_SECURITY = "AGENT_SECURITY", "Agent security"
    OTHER_AGENT = "OTHER_AGENT", "Other agent"


class MonitoringTier(models.TextChoices):
    NEW = "NEW", "New"
    HOT = "HOT", "Hot"
    RISING = "RISING", "Rising"
    NORMAL = "NORMAL", "Normal"
    STABLE = "STABLE", "Stable"
    DORMANT = "DORMANT", "Dormant"
    ARCHIVED = "ARCHIVED", "Archived"


class Topic(models.Model):
    name = models.CharField(max_length=100, unique=True)
    normalized_name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "topics"
        ordering = ("normalized_name",)

    def __str__(self) -> str:
        return self.name


class Repository(models.Model):
    github_id = models.BigIntegerField(unique=True)
    owner = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=512, unique=True)
    description = models.TextField(null=True, blank=True)  # noqa: DJ001 - GitHub null is meaningful
    homepage = models.TextField(null=True, blank=True)  # noqa: DJ001 - GitHub null is meaningful
    category = models.CharField(
        max_length=50,
        choices=RepositoryCategory.choices,
        default=RepositoryCategory.OTHER_AGENT,
        db_index=True,
    )
    stars = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    forks = models.PositiveBigIntegerField(null=True, blank=True)
    subscribers = models.PositiveBigIntegerField(null=True, blank=True)
    open_issues = models.PositiveBigIntegerField(null=True, blank=True)
    primary_language = models.CharField(  # noqa: DJ001 - GitHub null is meaningful
        max_length=100, null=True, blank=True
    )
    license_key = models.CharField(  # noqa: DJ001 - GitHub null is meaningful
        max_length=100, null=True, blank=True
    )
    license_spdx = models.CharField(  # noqa: DJ001 - GitHub null is meaningful
        max_length=100, null=True, blank=True
    )
    default_branch = models.CharField(max_length=255)
    repo_size = models.PositiveBigIntegerField(default=0)
    is_fork = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False, db_index=True)
    is_disabled = models.BooleanField(default=False)
    community_health = models.PositiveSmallIntegerField(null=True, blank=True)
    github_created_at = models.DateTimeField()
    github_updated_at = models.DateTimeField()
    github_pushed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_synced_at = models.DateTimeField(db_index=True)
    monitoring_tier = models.CharField(
        max_length=20,
        choices=MonitoringTier.choices,
        default=MonitoringTier.NORMAL,
        db_index=True,
    )
    monitoring_enabled = models.BooleanField(default=True, db_index=True)
    last_snapshot_at = models.DateTimeField(null=True, blank=True)
    next_snapshot_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    raw_metadata = models.JSONField(default=dict)
    topics = models.ManyToManyField(Topic, through="RepositoryTopic", related_name="repositories")

    class Meta:
        db_table = "repositories"
        ordering = ("-stars", "full_name")
        indexes = [
            models.Index(
                models.F("category"),
                models.F("is_disabled"),
                models.F("is_fork"),
                models.OrderBy(models.F("stars"), descending=True, nulls_last=True),
                name="repo_cat_stars_idx",
            ),
            models.Index(
                fields=("monitoring_enabled", "next_snapshot_at"),
                name="repo_snapshot_due_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name


class RepositoryTopic(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)

    class Meta:
        db_table = "repository_topics"
        constraints = [
            models.UniqueConstraint(
                fields=("repository", "topic"),
                name="unique_repository_topic",
            )
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name}: {self.topic.normalized_name}"


class RepositoryLocalization(models.Model):
    repository = models.OneToOneField(
        Repository, on_delete=models.CASCADE, related_name="zh_localization"
    )
    source_hash = models.CharField(max_length=64)
    description_zh = models.TextField()
    topics_zh = models.JSONField(default=list)
    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="TRANSLATED")
    translated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repository_localizations"

    def __str__(self) -> str:
        return f"{self.repository.full_name}: zh-CN"


class GitHubDiscoveryQuery(models.Model):
    query = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "github_discovery_queries"
        ordering = ("id",)

    def __str__(self) -> str:
        return self.query
