from rest_framework import serializers
from contents.models import  Grade
from .models import SubscriptionPlan, SubscriptionPlanPricing

class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = ['id', 'name']

class SubscriptionPlanSerializer(serializers.ModelSerializer):

    class Meta:
        model = SubscriptionPlan
        fields = '__all__'


class PaymentInitSerializer(serializers.Serializer):
    subscription_id = serializers.IntegerField()
    grade_id = serializers.IntegerField()
    period_type = serializers.ChoiceField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')])

    def validate(self, data):
        try:
            subscription = SubscriptionPlan.objects.get(id=data['subscription_id'])
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Invalid subscription ID")

        try:
            pricing = SubscriptionPlanPricing.objects.get(
                grade_id=data['grade_id'],
                period_type=data['period_type']
            )
        except SubscriptionPlanPricing.DoesNotExist:
            raise serializers.ValidationError("Invalid grade/period combination")

        data['subscription'] = subscription
        data['pricing'] = pricing
        return data