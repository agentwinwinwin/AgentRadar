from django.contrib import admin

from .models import RepositorySnapshot


@admin.register(RepositorySnapshot)
class RepositorySnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "repository",
        "snapshot_bucket",
        "stars",
        "forks",
        "data_completeness",
    )
    list_filter = ("snapshot_date",)
    search_fields = ("repository__full_name",)
