from django.contrib import admin

from .models import GitHubDiscoveryQuery, Repository, RepositoryTopic, Topic


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("full_name", "category", "stars", "is_archived", "last_synced_at")
    list_filter = ("category", "is_archived", "is_fork", "is_disabled")
    search_fields = ("full_name", "description")
    filter_horizontal = ()


admin.site.register(Topic)
admin.site.register(RepositoryTopic)
admin.site.register(GitHubDiscoveryQuery)
