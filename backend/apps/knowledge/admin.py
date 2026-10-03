from django.contrib import admin

from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeSyncState

admin.site.register(KnowledgeDocument)
admin.site.register(KnowledgeChunk)
admin.site.register(KnowledgeSyncState)
