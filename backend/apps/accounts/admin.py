from django.contrib import admin

from .models import Account, ProvidentFundProfile, UserSetting

admin.site.register([Account, ProvidentFundProfile, UserSetting])
