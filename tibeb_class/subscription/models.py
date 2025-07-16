from django.db import models
from django.utils import timezone
from datetime import timedelta

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
    price =models.DecimalField(blank=True,null=True,decimal_places=2,max_digits=100)
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
    






