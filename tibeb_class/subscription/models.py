from django.db import models
from django.utils import timezone
from datetime import timedelta

# Create your models here.
class SubscriptionPlan(models.Model):
    PLAN_TYPE_CHOICES = (
        ('freemium', 'Freemium'),
        ('grade_based', 'Grade Based'),
    )
    PERIOD_TYPE_CHOICES = (
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),

    )
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES)
    duration = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.plan_type})"
    
class SubscriptionPlanPricing(models.Model):
    PERIOD_TYPE_CHOICES = (
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),

    )
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='grade_pricings')
    grade = models.ForeignKey('contents.Grade', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    discount = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ('subscription_plan', 'grade')

    def __str__(self):
        return f"{self.subscription_plan.name} - {self.grade.name}: ${self.price}"
    






