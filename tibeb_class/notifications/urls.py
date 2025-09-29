# notifications/urls.py
from django.urls import path
from .views import get_user_notifications, mark_notification_read, mark_all_notifications_read

urlpatterns = [
    path("", get_user_notifications, name="get_user_notifications"),
    path("mark-read/<int:pk>/", mark_notification_read, name="mark_notification_read"),
    path("mark-all-read/", mark_all_notifications_read, name="mark_all_notifications_read"),
]
