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

    def __str__(self):
        return self.username
class ParentChild(models.Model):
    parent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='children')
    child = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='parents')
    Relation_Status = (
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
    )
    status = models.CharField(max_length=10, choices=Relation_Status, default='pending')

    class Meta:
        unique_together = ('parent', 'child')

    
class SubsectionProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='progress')
    subsection = models.ForeignKey('contents.Subsection', on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    watched_seconds = models.PositiveIntegerField(default=0)
    last_watched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'subsection')

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
