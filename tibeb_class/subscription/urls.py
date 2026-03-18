from django.urls import path
from .views import (
    get_subscription_plans,
    calculate_subscription_price,
    initialize_payment,
    chapa_webhook,
    get_active_subscriptions,
    get_payment_settings,
    upload_receipt,
    receipt_admin_login,
    assigned_receipts,
    review_receipt,
)

urlpatterns = [
    path('', get_subscription_plans, name='get_subscription_plans'),
    path('payment-settings/', get_payment_settings, name='get_payment_settings'),
    path('custome-subscription-price', calculate_subscription_price, name='calculate_subscription_price'),
    path('initialize-payment', initialize_payment, name='initialize_payment'),
    path('upload-receipt/', upload_receipt, name='upload_receipt'),
    path('admin-ui/login/', receipt_admin_login, name='receipt_admin_login'),
    path('admin-ui/receipts/', assigned_receipts, name='assigned_receipts'),
    path('admin-ui/receipts/<int:payment_id>/review/', review_receipt, name='review_receipt'),
    path('rpadmin/login/', receipt_admin_login, name='receipt_admin_login_rpadmin'),
    path('rpadmin/receipts/', assigned_receipts, name='assigned_receipts_rpadmin'),
    path('rpadmin/receipts/<int:payment_id>/review/', review_receipt, name='review_receipt_rpadmin'),
    path('chapa-webhook/', chapa_webhook, name='chapa_webhook'),
    path('active-subscriptions/', get_active_subscriptions, name='get_active_subscriptions'),

]
