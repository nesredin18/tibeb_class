from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta
import random


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('parent', 'Parent'),
    )
    UserName_Type = (
        ('email', 'Email'),
        ('phone', 'Phone'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    grades = models.ManyToManyField('contents.Grade', related_name='users', blank=True)
    is_verified = models.BooleanField(default=False)  # Add this line
    fcm_token = models.TextField(blank=True, null=True)
    last_email_change = models.DateTimeField(null=True, blank=True, default=timezone.now)
    username_type = models.CharField(max_length=10, choices=UserName_Type, default='email')
    pending_username = models.CharField(max_length=255, blank=True, null=True)
    pending_username_type = models.CharField(max_length=10, choices=UserName_Type, default='email',blank=True, null=True)
    def __str__(self):
        return self.username
class PhoneOTP(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.otp:
            self.otp = str(random.randint(100000, 999999))
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=20)
    
class PasswordResetOTP(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=20)

    def save(self, *args, **kwargs):
        if not self.otp:
            self.otp = str(random.randint(100000, 999999))
        super().save(*args, **kwargs)
class ChangeUserNameOTP(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=20)

    def save(self, *args, **kwargs):
        if not self.otp:
            self.otp = str(random.randint(100000, 999999))
        super().save(*args, **kwargs)
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
    watched_seconds = models.PositiveIntegerField(default=0)
    last_watched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user','video')
class BookProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='bookprogress')
    book = models.ForeignKey('contents.Book', on_delete=models.CASCADE, null=True, blank=True)
    read_pages = models.PositiveIntegerField(default=0)
    last_read_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user','book')
class ExerciseProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='exerciseprogress')
    exercise = models.ForeignKey('contents.Exercise', on_delete=models.CASCADE, null=True, blank=True)
    done_exercises = models.PositiveIntegerField(default=0)
    last_done_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user','exercise')
class QuestionProgress(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='question_progress')
    question = models.ForeignKey('contents.Question', on_delete=models.CASCADE, related_name='progress')
    exercise = models.ForeignKey('contents.Exercise', on_delete=models.CASCADE, related_name='question_progress')  # Optional but helpful for filtering
    answer_text = models.TextField(blank=True)  # For write type questions
    selected_option = models.ForeignKey('contents.Option', on_delete=models.SET_NULL, null=True, blank=True)  # For choose type
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'question','exercise')  # So a user can only have one record per question

    def __str__(self):
        return f"{self.user.username} - {self.question}"


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
    



class ExerciseAnswer(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='exercise_answers')
    exercise = models.ForeignKey('contents.Exercise', on_delete=models.CASCADE)
    question = models.ForeignKey('contents.Question', on_delete=models.CASCADE)
    selected_option = models.ForeignKey('contents.Option', on_delete=models.SET_NULL, null=True, blank=True)  # for 'choose' type
    written_answer = models.TextField(blank=True, null=True)  # for 'write' type
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'question','exercise')

    def __str__(self):
        return f"{self.user.username} - Q:{self.question.id} - {'Correct' if self.is_correct else 'Wrong'}"
