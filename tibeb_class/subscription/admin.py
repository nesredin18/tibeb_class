from django.contrib import admin
from .models import (
    Payment,
    SubscriptionPaymentConfiguration,
    SubscriptionPlan,
    SubscriptionPlanPricing,
    SubscriptionReceiptAdminProfile,
)

# Register your models here.
admin.site.register(SubscriptionPlan)
admin.site.register(SubscriptionPlanPricing)
admin.site.register(Payment)
admin.site.register(SubscriptionPaymentConfiguration)
admin.site.register(SubscriptionReceiptAdminProfile)
