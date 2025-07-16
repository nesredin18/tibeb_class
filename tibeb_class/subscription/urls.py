from django.urls import path
from .views import get_subscription_plans,calculate_subscription_price

urlpatterns = [
    path('', get_subscription_plans, name='get_subscription_plans'),
    path('custome-subscription-price', calculate_subscription_price, name='calculate_subscription_price'),


]