# notifications/urls.py
from django.urls import path
from .views import UserNotificationList

urlpatterns = [
    path('', UserNotificationList.as_view(), name='user-notifications'),
]
