from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import uuid

# Create your models here.
class SubscriptionPlan(models.Model):
    PLAN_TYPE_CHOICES = (
        ('freemium', 'Freemium'),
        ('grade_based', 'Grade Based'),
        ('premiume', 'Premiume'),
        ('special_offer', 'Special Offer')
    )
    PERIOD_TYPE_CHOICES = (
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),

    )
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)
    grades = models.ManyToManyField('contents.Grade', related_name='subscriptionplan')
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES)
    duration = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    expires= models.DateTimeField(blank=True,null=True)
    price =models.DecimalField(blank=True,null=True,decimal_places=2,max_digits=60)
    features = models.TextField(blank=True,null=True)
    rank = models.IntegerField(blank=True,null=True)
    isrecommended=models.BooleanField(blank=True,null=True,default=False)

    def __str__(self):
        return f"{self.name} ({self.plan_type})"
    
class SubscriptionPlanPricing(models.Model):
    PERIOD_TYPE_CHOICES = (
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),

    )
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)
    grade = models.ForeignKey('contents.Grade', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    discount = models.DecimalField(max_digits=4, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ( 'grade','period_type')

    def __str__(self):
        return f"{self.grade.name} - {self.period_type}"
    
class Payment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('expired', 'Expired'),
    )
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    gift_from = models.ForeignKey( settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='gift_payments')
    provider = models.CharField(max_length=30, default='chapa')
    receipt_file = models.FileField(upload_to='subscription_payment_receipts/', blank=True, null=True)
    assigned_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_subscription_receipts'
    )
    selected_receipt_account = models.ForeignKey(
        'SubscriptionReceiptAdminBankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_subscription_receipts'
    )
    review_note = models.TextField(blank=True)
    receipt_uploaded_at = models.DateTimeField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    grade = models.ManyToManyField('contents.Grade', blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES , default='pending')

    chapa_tx_ref = models.CharField(max_length=100, blank=True, null=True, unique=True)

    # New fields
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(blank=True, null=True)
    period_type = models.CharField(max_length=100,blank=True,null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} - {self.amount} ETB - {self.status}"


class SubscriptionPaymentConfiguration(models.Model):
    PAYMENT_MODE_CHOICES = (
        ('chapa', 'Chapa'),
        ('receipt', 'Receipt'),
    )
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES, default='chapa')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subscription payment configuration"
        verbose_name_plural = "Subscription payment configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Subscription payment configuration"


class SubscriptionReceiptAdminProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription_receipt_admin_profile')
    bank_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    rotation_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['rotation_order', 'id']

    def __str__(self):
        return f"{self.user.username} - {self.bank_name}"


class SubscriptionReceiptAdminBankAccount(models.Model):
    profile = models.ForeignKey(
        SubscriptionReceiptAdminProfile,
        on_delete=models.CASCADE,
        related_name='bank_accounts',
    )
    bank_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=120)
    account_holder_name = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['rank', 'id']

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"
    






