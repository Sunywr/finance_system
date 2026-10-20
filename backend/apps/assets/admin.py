from django.contrib import admin

from .models import Asset, AssetValuation

admin.site.register([Asset, AssetValuation])
