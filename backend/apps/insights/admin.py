from django.contrib import admin

from .models import AIAnalysis, AIProviderConfig

admin.site.register([AIProviderConfig, AIAnalysis])
