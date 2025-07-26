from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('parent', 'Parent'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    grades = models.ManyToManyField('contents.Grade', related_name='users', blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False)  # Add this line


    def __str__(self):
        return self.username
class ParentChild(models.Model):
    parent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='children')
    child = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='parents')
    Relation_Status = (
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
        ('canceled', 'Canceled'),
        ('unlinked','UnLinked')
    )
    status = models.CharField(max_length=10, choices=Relation_Status, default='pending')

    class Meta:
        unique_together = ('parent', 'child')

    
class VideoProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='videoprogress')
    video = models.ForeignKey('contents.Video', on_delete=models.CASCADE, null=True, blank=True)
    completed_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    watched_seconds = models.PositiveIntegerField(default=0)
    last_watched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user','video')
class BookProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='bookprogress')
    book = models.ForeignKey('contents.Book', on_delete=models.CASCADE, null=True, blank=True)
    completed_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    read_pages = models.PositiveIntegerField(default=0)
    last_read_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user','book')
class ExerciseProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='exerciseprogress')
    exercise = models.ForeignKey('contents.Exercise', on_delete=models.CASCADE, null=True, blank=True)
    completed_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    done_exercises = models.PositiveIntegerField(default=0)
    last_done_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user','exercise')

class UserSubscription(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='subscriptions')
    subscription_plan = models.ForeignKey('subscription.SubscriptionPlan', on_delete=models.CASCADE)
    grade = models.ForeignKey('contents.Grade', on_delete=models.SET_NULL, null=True, blank=True)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    Payment_Status = (
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
    )
    payment_status = models.CharField(max_length=10, choices=Payment_Status, default='unpaid')
    Status= (
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('pending', 'Pending'),
    )
    status = models.CharField(max_length=10, choices=Status, default='active')

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=self.subscription_plan.duration)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.subscription_plan.name}"
    
class User_Grade(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='user_grades')
    grade = models.ForeignKey('contents.Grade', on_delete=models.CASCADE, related_name='user_grades')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'grade')

    def __str__(self):
        return f"{self.user.username} - {self.grade.name}"
