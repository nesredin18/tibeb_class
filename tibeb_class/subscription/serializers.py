from rest_framework import serializers
from django.contrib.auth import get_user_model
from contents.models import  Grade
from .models import Payment, SubscriptionPlan, SubscriptionPlanPricing, SubscriptionPaymentConfiguration, SubscriptionReceiptAdminProfile, SubscriptionReceiptAdminBankAccount

User = get_user_model()

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
    receipt_file_url = serializers.SerializerMethodField()
    user_identifier = serializers.SerializerMethodField()
    assigned_admin_name = serializers.SerializerMethodField()
    selected_receipt_account = serializers.SerializerMethodField()

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
            "user_identifier",
            "assigned_admin",
            "assigned_admin_name",
            "selected_receipt_account",
            "reviewed_by",
            "review_note",
            "receipt_uploaded_at",
            "reviewed_at",
            "receipt_file",
            "receipt_file_url",
            "start_date",
            "end_date",
            "period_type",
            "chapa_tx_ref",
            "provider",
            "created_at",
            "updated_at",
        ]

    def get_receipt_file_url(self, obj):
        if obj.receipt_file:
            return obj.receipt_file.url
        return None

    def get_user_identifier(self, obj):
        return getattr(obj.user, "username", "")

    def get_assigned_admin_name(self, obj):
        if not obj.assigned_admin:
            return None
        return getattr(obj.assigned_admin, "username", None)

    def get_selected_receipt_account(self, obj):
        if obj.selected_receipt_account:
            return SubscriptionReceiptAdminBankAccountSerializer(obj.selected_receipt_account).data
        profile = getattr(obj.assigned_admin, "subscription_receipt_admin_profile", None)
        accounts = _serialize_receipt_accounts(profile)
        return accounts[0] if accounts else None


class SubscriptionPaymentConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPaymentConfiguration
        fields = ["payment_mode"]


class UploadSubscriptionReceiptSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField(required=False)
    bank_account_id = serializers.IntegerField(required=False)
    receipt_file = serializers.FileField()


class SubscriptionReceiptAdminBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionReceiptAdminBankAccount
        fields = ["id", "bank_name", "account_number", "account_holder_name", "is_active", "rank"]


def _serialize_receipt_accounts(profile):
    if not profile:
        return []
    accounts = list(profile.bank_accounts.filter(is_active=True).order_by("rank", "id"))
    if accounts:
        return SubscriptionReceiptAdminBankAccountSerializer(accounts, many=True).data
    if profile.bank_name and profile.account_number:
        return [{
            "id": None,
            "bank_name": profile.bank_name,
            "account_number": profile.account_number,
            "account_holder_name": profile.user.get_full_name() if hasattr(profile.user, "get_full_name") else "",
            "is_active": profile.is_active,
            "rank": 0,
        }]
    return []


class SubscriptionReceiptAdminProfileSerializer(serializers.ModelSerializer):
    bank_accounts = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionReceiptAdminProfile
        fields = ["id", "bank_name", "account_number", "rotation_order", "is_active", "bank_accounts"]

    def get_bank_accounts(self, obj):
        return _serialize_receipt_accounts(obj)


class SubscriptionReceiptAdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class SubscriptionReceiptReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[("approve", "approve"), ("decline", "decline")])
    note = serializers.CharField(required=False, allow_blank=True)
