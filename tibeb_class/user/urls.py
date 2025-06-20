from django.urls import path
from .views import signup, login, test
from .views import get_user_info, get_pending_requests, get_accepted_requests, get_progress
from .views import create_user_subscription, get_active_subscription

urlpatterns = [
    path('signup/', signup, name='signup'),
    path('login/', login, name='login'),
    path('test/', test, name='test'),
    path('user/info/', get_user_info, name='user-info'),
    path('student/parent-requests/', get_pending_requests, name='parent-requests'),
    path('student/accepted-requests/', get_accepted_requests, name='accepted-requests'),
    path('student/progress/', get_progress, name='student-progress'),
    path('student/create-subscription/', create_user_subscription, name='create-subscription'),
    path('student/active-subscription/', get_active_subscription, name='active-subscription'),
]
