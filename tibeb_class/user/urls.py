from django.urls import path
from .views import signup, login, test

urlpatterns = [
    path('signup/', signup, name='signup'),
    path('login/', login, name='login'),
    path('test/', test, name='test'),
]
