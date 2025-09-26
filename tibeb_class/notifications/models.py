
# Create your models here.
# notifications/models.py
from django.db import models
from django.conf import settings

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('book', 'Book'),
        ('video', 'Video'),
        ('exercise', 'Exercise'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    content_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    content_id = models.PositiveIntegerField()  # ID of Book, Video, or Exercise
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.message[:50]}"
