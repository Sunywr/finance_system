from django.contrib import admin

from .models import AccountTransfer, Category, InstallmentPeriod, InstallmentPlan, Tag, Transaction

admin.site.register([Category, Tag, Transaction, AccountTransfer, InstallmentPlan, InstallmentPeriod])
