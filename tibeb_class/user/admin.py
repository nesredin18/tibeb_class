from django.contrib import admin
from .models import CustomUser, UserSubscription,VideoProgress,BookProgress,ExerciseProgress,QuestionProgress

# Register your models here.
admin.site.register(CustomUser)
admin.site.register(UserSubscription)
admin.site.register(VideoProgress)
admin.site.register(BookProgress)
admin.site.register(ExerciseProgress)
admin.site.register(QuestionProgress)



