from django.contrib import admin

from .models import Loan, LoanSchedule, OffsetPlan

admin.site.register([Loan, LoanSchedule, OffsetPlan])
