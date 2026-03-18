from django.contrib import admin
from .models import (
    Payment,
    SubscriptionPaymentConfiguration,
    SubscriptionPlan,
    SubscriptionPlanPricing,
    SubscriptionReceiptAdminBankAccount,
    SubscriptionReceiptAdminProfile,
)

# Register your models here.
admin.site.register(SubscriptionPlan)
admin.site.register(SubscriptionPlanPricing)
admin.site.register(Payment)
admin.site.register(SubscriptionPaymentConfiguration)


class SubscriptionReceiptAdminBankAccountInline(admin.TabularInline):
    model = SubscriptionReceiptAdminBankAccount
    extra = 1
    fields = ('bank_name', 'account_number', 'account_holder_name', 'is_active', 'rank')


@admin.register(SubscriptionReceiptAdminProfile)
class SubscriptionReceiptAdminProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'bank_name', 'account_number', 'rotation_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'bank_name', 'account_number')
    inlines = [SubscriptionReceiptAdminBankAccountInline]


admin.site.register(SubscriptionReceiptAdminBankAccount)
