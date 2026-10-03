from django.contrib import admin

from .models import Contributor, RepositoryActivityMetric, RepositoryContributor, RepositoryRelease

admin.site.register(RepositoryActivityMetric)
admin.site.register(Contributor)
admin.site.register(RepositoryContributor)
admin.site.register(RepositoryRelease)
