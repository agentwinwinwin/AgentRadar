from django.contrib import admin

from .models import (
    AcquisitionQueryShard,
    HistoricalActivityBucket,
    HistoricalActivityWindow,
    HistoricalBackfillBatch,
    HistoricalBackfillBatchItem,
    HistoricalContributorWeek,
    HistoricalSourceCache,
    RepositoryPool,
    RepositoryPoolMembership,
    TrainingSample,
)

admin.site.register(HistoricalActivityWindow)
admin.site.register(HistoricalActivityBucket)
admin.site.register(HistoricalContributorWeek)
admin.site.register(HistoricalSourceCache)
admin.site.register(TrainingSample)
admin.site.register(HistoricalBackfillBatch)
admin.site.register(HistoricalBackfillBatchItem)
admin.site.register(RepositoryPool)
admin.site.register(RepositoryPoolMembership)
admin.site.register(AcquisitionQueryShard)
