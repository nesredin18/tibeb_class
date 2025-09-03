from django.urls import path
from .views import get_subscription_plans,calculate_subscription_price,initialize_payment,chapa_webhook

urlpatterns = [
    path('', get_subscription_plans, name='get_subscription_plans'),
    path('custome-subscription-price', calculate_subscription_price, name='calculate_subscription_price'),
    path('initialize-payment', initialize_payment, name='initialize_payment'),
    path('chapa-webhook/', chapa_webhook, name='chapa_webhook'),

]