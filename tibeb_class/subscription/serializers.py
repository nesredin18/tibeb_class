from rest_framework import serializers
from contents.models import  Grade
from .models import Payment, SubscriptionPlan, SubscriptionPlanPricing, SubscriptionPaymentConfiguration, SubscriptionReceiptAdminProfile

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
    
class PaymentSerializer(serializers.ModelSerializer):
    subscription_plan_name = serializers.CharField(source="subscription_plan.name", read_only=True)
    grade_names = serializers.SlugRelatedField(
        many=True, slug_field="name", read_only=True, source="grade"
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "subscription_plan",
            "subscription_plan_name",
            "grade",
            "grade_names",
            "amount",
            "status",
            "payment_status",
            "start_date",
            "end_date",
            "period_type",
            "chapa_tx_ref",
            "provider",
            "created_at",
            "updated_at",
        ]


class SubscriptionPaymentConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPaymentConfiguration
        fields = ["payment_mode"]


class UploadSubscriptionReceiptSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField()
    receipt_file = serializers.FileField()


class SubscriptionReceiptAdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionReceiptAdminProfile
        fields = ["id", "bank_name", "account_number", "rotation_order", "is_active"]
