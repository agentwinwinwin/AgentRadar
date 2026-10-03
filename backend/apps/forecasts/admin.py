from django.contrib import admin

from .models import MLModel, RepositoryForecast

admin.site.register(MLModel)
admin.site.register(RepositoryForecast)
