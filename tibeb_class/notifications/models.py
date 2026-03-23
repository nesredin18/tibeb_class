
# Create your models here.
# notifications/models.py
from django.db import models
from django.conf import settings

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('book', 'Book'),
        ('video', 'Video'),
        ('exercise', 'Exercise'),
        ('parent_request', 'Parent Request'),
    )    
    Resource_Type = (
        ('class', 'Class'),
        ('additional', 'Additional'),
        ('system', 'System'),
    )
    type = models.CharField(max_length=20, choices=Resource_Type, default='class')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    content_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    content_id = models.PositiveIntegerField()  # ID of Book, Video, or Exercise
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    target_grade_id = models.PositiveIntegerField(null=True, blank=True)
    target_subject_id = models.PositiveIntegerField(null=True, blank=True)
    target_chapter_id = models.PositiveIntegerField(null=True, blank=True)
    target_subsection_id = models.PositiveIntegerField(null=True, blank=True)
    level = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.user.username} - {self.message[:50]}"

# notifications/models.py
from django.db import models

class NotificationQueue(models.Model):
    CONTENT_TYPES = (
        ('book', 'Book'),
        ('video', 'Video'),
        ('exercise', 'Exercise'),
    )
    Resource_Type = (
        ('class', 'Class'),
        ('additional', 'Additional'),
    )
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES)
    content_id = models.PositiveIntegerField()
    content_grade_id = models.PositiveIntegerField(null=True, blank=True)  # ✅ Add this line
    message = models.CharField(max_length=255)
    target_grade_id = models.PositiveIntegerField(null=True, blank=True)
    target_subject_id = models.PositiveIntegerField(null=True, blank=True)
    target_chapter_id = models.PositiveIntegerField(null=True, blank=True)
    target_subsection_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=20, choices=Resource_Type, default='class')
    level = models.CharField(max_length=20)


    def __str__(self):
        return f"Queue: {self.message} ({self.content_type})"

