from django.contrib import admin

from .models import CreditCard, CreditCardBill, DebtItem, DebtPayment, RecurringDebt

admin.site.register([CreditCard, CreditCardBill, RecurringDebt, DebtItem, DebtPayment])
