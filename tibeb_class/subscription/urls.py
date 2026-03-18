from django.urls import path
from .views import (
    get_subscription_plans,
    calculate_subscription_price,
    initialize_payment,
    chapa_webhook,
    get_active_subscriptions,
    get_payment_settings,
    upload_receipt,
)

urlpatterns = [
    path('', get_subscription_plans, name='get_subscription_plans'),
    path('payment-settings/', get_payment_settings, name='get_payment_settings'),
    path('custome-subscription-price', calculate_subscription_price, name='calculate_subscription_price'),
    path('initialize-payment', initialize_payment, name='initialize_payment'),
    path('upload-receipt/', upload_receipt, name='upload_receipt'),
    path('chapa-webhook/', chapa_webhook, name='chapa_webhook'),
    path('active-subscriptions/', get_active_subscriptions, name='get_active_subscriptions'),

]
