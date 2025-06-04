from django.contrib import admin
from .models import CustomUser, UserSubscription, SubsectionProgress

# Register your models here.
admin.site.register(CustomUser)
admin.site.register(UserSubscription)
admin.site.register(SubsectionProgress)
