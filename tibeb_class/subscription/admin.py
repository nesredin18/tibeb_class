from django.contrib import admin
from .models import SubscriptionPlan,SubscriptionPlanPricing

# Register your models here.
admin.site.register(SubscriptionPlan)
admin.site.register(SubscriptionPlanPricing)
