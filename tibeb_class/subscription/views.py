from datetime import timedelta
import json
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from contents.models import Grade
from tibeb_class.permissions import IsVerified
from user.models import CustomUser, ParentChild
from .models import Payment, SubscriptionPlan,SubscriptionPlanPricing, SubscriptionPaymentConfiguration, SubscriptionReceiptAdminProfile, SubscriptionReceiptAdminBankAccount
from .serializers import (
    PaymentInitSerializer,
    PaymentSerializer,
    SubscriptionPlanSerializer,
    SubscriptionPaymentConfigurationSerializer,
    SubscriptionReceiptAdminProfileSerializer,
    SubscriptionReceiptAdminLoginSerializer,
    SubscriptionReceiptReviewSerializer,
    UploadSubscriptionReceiptSerializer,
)
from rest_framework import status
from decimal import Decimal
import uuid,requests
from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Payment
import hmac
import hashlib
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from tibeb_class.email_templates import EmailTemplateHelper
from user.utils import send_sms_otp






@api_view(['GET'])
def get_subscription_plans(request):
    plans = SubscriptionPlan.objects.filter(is_active=True).prefetch_related('grades')
    serializer = SubscriptionPlanSerializer(plans, many=True)
    return Response({
        "plans": serializer.data
    })


@api_view(['POST'])
def calculate_subscription_price(request):
    data = request.data

    grade_ids = data.get('grades', [])
    period_type = data.get('period_type')
    duration = data.get('duration')

    if not all([ grade_ids, period_type, duration]):
        return Response({'error': 'Missing required fields.'}, status=status.HTTP_400_BAD_REQUEST)


    total_price_grade = Decimal('0.00')
    total_price= Decimal('0.00')
    grade_prices = []
    if duration>12:
        period_type="yearly"

    for grade_id in grade_ids:
        try:
            pricing = SubscriptionPlanPricing.objects.get(
                grade_id=grade_id,
                period_type=period_type
            )
        except SubscriptionPlanPricing.DoesNotExist:
            return Response({'error': f'Pricing not found for grade ID {grade_id}.'}, status=status.HTTP_404_NOT_FOUND)

        total_price_grade = pricing.price * Decimal(duration)
        discounted_price = total_price_grade * Decimal((pricing.discount)/100)
        total_price_grade -= discounted_price
        total_price+=total_price_grade


        grade_prices.append({
            'grade_id': grade_id,
            'base_price': float(pricing.price),
            'discount': float(pricing.discount),
            'discounted_price_per_period': float(discounted_price),
            'total_price_for_duration': float(total_price_grade)
        })

    return Response({
        'period_type': period_type,
        'duration': duration,
        'grades': grade_prices,
        'total_price': round(float(total_price), 2)
    })



CHAPA_API_KEY = settings.CHAPA_API_KEY
CHAPA_INIT_URL = settings.CHAPA_INIT_URL
CHAPA_CALLBACK_URL = settings.CHAPA_CALLBACK_URL
DEFAULT_RETURN_URL = settings.DEFAULT_RETURN_URL


def _get_payment_config():
    return SubscriptionPaymentConfiguration.load()


def _pick_receipt_admin():
    profiles = list(SubscriptionReceiptAdminProfile.objects.filter(is_active=True, user__is_active=True).order_by('rotation_order', 'id'))
    if not profiles:
        return None
    receipt_count = Payment.objects.filter(provider='receipt').count()
    return profiles[receipt_count % len(profiles)].user


def _get_receipt_accounts(profile):
    if not profile:
        return []
    accounts = list(profile.bank_accounts.filter(is_active=True).order_by('rank', 'id'))
    if accounts:
        return accounts
    return []


def _is_super_receipt_admin(user):
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))


def _build_receipt_admin_summary(queryset, admin_user=None):
    if admin_user is not None:
        queryset = queryset.filter(assigned_admin=admin_user)
    approved = queryset.filter(payment_status='completed')
    declined = queryset.filter(payment_status='failed')
    pending = queryset.filter(payment_status='pending')
    return {
        'approved_count': approved.count(),
        'approved_amount': str(approved.aggregate(total=Sum('amount')).get('total') or Decimal('0')),
        'declined_count': declined.count(),
        'declined_amount': str(declined.aggregate(total=Sum('amount')).get('total') or Decimal('0')),
        'pending_count': pending.count(),
        'pending_amount': str(pending.aggregate(total=Sum('amount')).get('total') or Decimal('0')),
    }


def _get_user_notification_contact(user):
    username_type = (getattr(user, 'username_type', '') or '').strip().lower()
    username = (getattr(user, 'username', '') or '').strip()
    email = (getattr(user, 'email', '') or '').strip()
    phone = (getattr(user, 'phone_number', '') or '').strip()
    if username_type == 'email':
        return email or username, 'email'
    if username_type == 'phone':
        return phone or username, 'phone'
    if email:
        return email, 'email'
    if phone:
        return phone, 'phone'
    return '', ''


def _send_receipt_approved_notification(user):
    target, contact_type = _get_user_notification_contact(user)
    if not target:
        return
    html = f"""
    <div style="font-family:'Roboto',Arial,sans-serif;background-color:#f9fafb;padding:0;margin:0;">
      <div style="max-width:600px;margin:0 auto;background-color:#ffffff;">
        {EmailTemplateHelper._header()}
        <div style="padding:32px 24px;max-width:600px;margin:0 auto;">
          <h1 style="font-size:24px;text-align:center;font-weight:bold;color:#111827;margin:0 0 16px;">
            Receipt Payment Approved
          </h1>
          <p style="color:#4b5563;font-size:14px;margin:0 0 24px;">
            Your Tibeb Class receipt payment was approved successfully.
          </p>
        </div>
        {EmailTemplateHelper._footer()}
      </div>
    </div>
    """
    if contact_type == 'email':
        msg = EmailMultiAlternatives(
            subject="Tibeb Class Receipt Payment Approved",
            body=strip_tags(html),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[target],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    else:
        send_sms_otp(target, "Your Tibeb Class receipt payment was approved successfully.")


def _send_receipt_rejected_notification(user):
    target, contact_type = _get_user_notification_contact(user)
    if not target:
        return
    if contact_type == 'email':
        html = f"""
        <div style="font-family:'Roboto',Arial,sans-serif;background-color:#f9fafb;padding:0;margin:0;">
          <div style="max-width:600px;margin:0 auto;background-color:#ffffff;">
            {EmailTemplateHelper._header()}
            <div style="padding:32px 24px;max-width:600px;margin:0 auto;">
              <h1 style="font-size:24px;text-align:center;font-weight:bold;color:#111827;margin:0 0 16px;">
                Receipt Payment Rejected
              </h1>
              <p style="color:#4b5563;font-size:14px;margin:0 0 24px;">
                Your Tibeb Class receipt payment was rejected. Please upload a valid receipt or contact support.
              </p>
            </div>
            {EmailTemplateHelper._footer()}
          </div>
        </div>
        """
        msg = EmailMultiAlternatives(
            subject="Tibeb Class Receipt Payment Rejected",
            body=strip_tags(html),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[target],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    else:
        send_sms_otp(target, "Your Tibeb Class receipt payment was rejected. Please upload a valid receipt or contact support.")


def _build_receipt_admin_token(user):
    refresh = RefreshToken.for_user(user)
    refresh["iss"] = settings.SIMPLE_JWT.get("ISSUER")
    refresh["aud"] = settings.SIMPLE_JWT.get("AUDIENCE")
    refresh["platform"] = "tibebclass-receipt-admin"
    return {
        "token": str(refresh.access_token),
        "refresh": str(refresh),
    }


def _is_receipt_manager(user):
    return bool(
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or hasattr(user, "subscription_receipt_admin_profile")
    )


@api_view(['GET'])
def get_payment_settings(request):
    serializer = SubscriptionPaymentConfigurationSerializer(_get_payment_config())
    return Response(serializer.data)


def _resolve_subscription_target_user(request, for_whom, other_email):
    if for_whom == "self":
        return request.user
    if for_whom == "other":
        if not other_email:
            raise ValueError('other_email is required when for_whom is "other"')
        try:
            return CustomUser.objects.get(username=other_email)
        except CustomUser.DoesNotExist as exc:
            raise LookupError('User not found.') from exc
    raise ValueError('Invalid for_whom value.')


def _prepare_subscription_payment(request, data):
    subscription_id = data.get("subscription_id")
    for_whom = data.get("for_whom")
    other_email = data.get("other_email")
    duration = data.get("duration")
    period_type = data.get("period_type")
    grades = data.get("grades", [])
    if isinstance(grades, str):
        try:
            grades = json.loads(grades)
        except json.JSONDecodeError:
            grades = [value for value in grades.split(",") if value]

    subscription = None
    amount = None
    user = _resolve_subscription_target_user(request, for_whom, other_email)

    if subscription_id:
        try:
            subscription = SubscriptionPlan.objects.get(id=subscription_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise ValueError("Invalid subscription plan")
        amount = subscription.price
        duration = subscription.duration
        period_type = subscription.period_type
    else:
        if not duration or not period_type or not grades:
            raise ValueError("duration, period_type, and grades are required for custom plan")
        try:
            duration = int(duration)
        except ValueError as exc:
            raise ValueError("Duration must be an integer") from exc

        if duration > 12:
            period_type = "yearly"

        grade_objs = Grade.objects.filter(id__in=grades)
        if not grade_objs.exists() or grade_objs.count() != len(grades):
            raise ValueError("Invalid grades provided")

        total_price = Decimal("0.00")
        for grade in grade_objs:
            try:
                pricing = SubscriptionPlanPricing.objects.get(grade=grade, period_type=period_type)
            except SubscriptionPlanPricing.DoesNotExist as exc:
                raise LookupError(f"No pricing for grade {grade.name} and {period_type}") from exc
            total_price_grade = pricing.price * Decimal(duration)
            discount_amount = total_price_grade * (pricing.discount / Decimal("100"))
            total_price += total_price_grade - discount_amount

        amount = round(float(total_price), 2)

    last_active = Payment.objects.filter(
        user=user,
        status="active",
        payment_status="completed",
        end_date__gt=timezone.now()
    ).order_by("-end_date").first()

    last_pending = Payment.objects.filter(
        user=user,
        status="pending",
        payment_status="pending"
    ).order_by("-created_at").first()

    if last_active:
        start_date = last_active.end_date + timedelta(seconds=1)
        status_value = "pending"
        payment_status_value = "pending"
    elif last_pending:
        last_paid = Payment.objects.filter(
            user=user,
            status="active",
            payment_status="completed",
            end_date__gt=timezone.now()
        ).order_by("-end_date").first()

        if last_paid:
            start_date = last_paid.end_date + timedelta(seconds=1)
            status_value = "pending"
        else:
            start_date = timezone.now()
            status_value = "active"
        payment_status_value = "pending"
    else:
        start_date = timezone.now()
        status_value = "active"
        payment_status_value = "pending"

    if period_type == "monthly":
        end_date = start_date + timedelta(days=30 * int(duration))
    elif period_type == "yearly":
        end_date = start_date + timedelta(days=365 * int(duration))
    else:
        raise ValueError("Invalid period type")

    return {
        "user": user,
        "subscription": subscription,
        "amount": amount,
        "duration": duration,
        "period_type": period_type,
        "grades": grades,
        "start_date": start_date,
        "end_date": end_date,
        "status_value": status_value,
        "payment_status_value": payment_status_value,
        "gift_from": request.user if for_whom == "other" else None,
    }


def _create_subscription_receipt_payment(prepared, selected_account=None):
    tx_ref = str(uuid.uuid4())
    assigned_admin = selected_account.profile.user if selected_account else _pick_receipt_admin()
    payment = Payment.objects.create(
        user=prepared["user"],
        gift_from=prepared["gift_from"],
        provider='receipt',
        subscription_plan=prepared["subscription"],
        amount=prepared["amount"],
        chapa_tx_ref=tx_ref,
        start_date=prepared["start_date"],
        end_date=prepared["end_date"],
        period_type=prepared["period_type"],
        status=prepared["status_value"],
        payment_status=prepared["payment_status_value"],
        assigned_admin=assigned_admin,
        selected_receipt_account=selected_account,
    )
    if not prepared["subscription"] and prepared["grades"]:
        payment.grade.set(prepared["grades"])
    elif prepared["subscription"] and prepared["subscription"].grades.exists():
        payment.grade.set(prepared["subscription"].grades.all())
    return payment



@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
def initialize_payment(request):
    return_url = request.data.get("return_url") or DEFAULT_RETURN_URL
    payment_config = _get_payment_config()

    try:
        prepared = _prepare_subscription_payment(request, request.data)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except LookupError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

    if payment_config.payment_mode == 'receipt':
        assigned_admin = _pick_receipt_admin()
        assigned_profile = getattr(assigned_admin, 'subscription_receipt_admin_profile', None) if assigned_admin else None
        serialized_profile = SubscriptionReceiptAdminProfileSerializer(assigned_profile).data if assigned_profile else None
        return Response({
            "payment_mode": "receipt",
            "amount": prepared["amount"],
            "period_type": prepared["period_type"],
            "subscription_plan_name": prepared["subscription"].name if prepared["subscription"] else "Custom Subscription",
            "bank_assignment": serialized_profile,
            "bank_accounts": serialized_profile.get("bank_accounts", []) if serialized_profile else [],
        }, status=status.HTTP_200_OK)

    tx_ref = str(uuid.uuid4())
    payment = Payment.objects.create(
        user=prepared["user"],
        gift_from=prepared["gift_from"],
        provider='chapa',
        subscription_plan=prepared["subscription"],
        amount=prepared["amount"],
        chapa_tx_ref=tx_ref,
        start_date=prepared["start_date"],
        end_date=prepared["end_date"],
        period_type=prepared["period_type"],
        status=prepared["status_value"],
        payment_status=prepared["payment_status_value"],
    )
    if not prepared["subscription"] and prepared["grades"]:
        payment.grade.set(prepared["grades"])
    elif prepared["subscription"] and prepared["subscription"].grades.exists():
        payment.grade.set(prepared["subscription"].grades.all())

    payload = {
        "amount": str(prepared["amount"]),
        "currency": "ETB",
        "email": prepared["user"].email,
        "first_name": prepared["user"].first_name or "Customer",
        "last_name": prepared["user"].last_name or "",
        "tx_ref": tx_ref,
        "return_url": return_url,
    }
    headers = {
        "Authorization": f"Bearer {CHAPA_API_KEY}",
        "Content-Type": "application/json",
    }

    chapa_response = requests.post(CHAPA_INIT_URL, json=payload, headers=headers).json()

    if chapa_response.get("status") == "success":
        return Response({
            "checkout_url": chapa_response["data"]["checkout_url"],
            "tx_ref": tx_ref
        }, status=status.HTTP_200_OK)

    return Response({"error": "Failed to initialize payment"}, status=status.HTTP_400_BAD_REQUEST)

    subscription_id = request.data.get("subscription_id")
    for_whom = request.data.get("for_whom")
    other_email = request.data.get("other_email")
    duration = request.data.get("duration")
    period_type = request.data.get("period_type")
    grades = request.data.get("grades", [])
    return_url = request.data.get("return_url")

    tx_ref = str(uuid.uuid4())
    payment_config = _get_payment_config()

    subscription = None
    amount = None
    start_date = timezone.now()
    end_date = None

    if not return_url:
        return_url = DEFAULT_RETURN_URL
    if for_whom == "self":
        user = request.user
    elif for_whom == "other":
        if not other_email:
            return Response({'error': 'other_email is required when for_whom is "other"'}, status=400)
        try:
            user = CustomUser.objects.get(username=other_email)
        except CustomUser.DoesNotExist:
            return Response({'error': 'User not found.'}, status=404)
    else:
        return Response({'error': 'Invalid for_whom value.'}, status=400)
    # -----------------------
    # Case 1: Subscription plan
    # -----------------------
    if subscription_id:
        try:
            subscription = SubscriptionPlan.objects.get(id=subscription_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Invalid subscription plan"}, status=status.HTTP_400_BAD_REQUEST)

        amount = subscription.price
        duration = subscription.duration
        period_type = subscription.period_type

    # -----------------------
    # Case 2: Custom plan
    # -----------------------
    else:
        if not duration or not period_type or not grades:
            return Response(
                {"error": "duration, period_type, and grades are required for custom plan"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            duration = int(duration)
        except ValueError:
            return Response({"error": "Duration must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if duration > 12:
            period_type = "yearly"

        grade_objs = Grade.objects.filter(id__in=grades)
        if not grade_objs.exists() or grade_objs.count() != len(grades):
            return Response({"error": "Invalid grades provided"}, status=status.HTTP_400_BAD_REQUEST)

        total_price = Decimal("0.00")
        for grade in grade_objs:
            try:
                pricing = SubscriptionPlanPricing.objects.get(grade=grade, period_type=period_type)
            except SubscriptionPlanPricing.DoesNotExist:
                return Response(
                    {"error": f"No pricing for grade {grade.name} and {period_type}"},
                    status=status.HTTP_404_NOT_FOUND
                )
            total_price_grade = pricing.price * Decimal(duration)
            discount_amount = total_price_grade * (pricing.discount / Decimal("100"))
            total_price += total_price_grade - discount_amount

        amount = round(float(total_price), 2)

    # -----------------------
    # Decide start_date / status
    # -----------------------
    last_active = Payment.objects.filter(
        user=user,
        status="active",
        payment_status="completed",
        end_date__gt=timezone.now()
    ).order_by("-end_date").first()

    last_pending = Payment.objects.filter(
        user=user,
        status="pending",
        payment_status="pending"
    ).order_by("-created_at").first()

    if last_active:
        # User has an active subscription → queue
        start_date = last_active.end_date + timedelta(seconds=1)
        status_value = "pending"
        payment_status_value = "pending"

    elif last_pending:
        # User has pending → use last paid active subscription’s expiry
        last_paid = Payment.objects.filter(
            user=user,
            status="active",
            payment_status="completed",
            end_date__gt=timezone.now()
        ).order_by("-end_date").first()

        if last_paid:
            start_date = last_paid.end_date + timedelta(seconds=1)
            status_value = "pending"
        else:
            start_date = timezone.now()
            status_value = "active"

        payment_status_value = "pending"

    else:
        # First-time subscription → active now
        start_date = timezone.now()
        status_value = "active"
        payment_status_value = "pending"

    # -----------------------
    # Calculate end_date
    # -----------------------
    if period_type == "monthly":
        end_date = start_date + timedelta(days=30 * int(duration))
    elif period_type == "yearly":
        end_date = start_date + timedelta(days=365 * int(duration))
    else:
        return Response({"error": "Invalid period type"}, status=status.HTTP_400_BAD_REQUEST)

    # -----------------------
    # Create Payment
    # -----------------------
    payment = Payment.objects.create(
        user=user,
        gift_from=request.user if for_whom=="other" else None,
        provider='receipt' if payment_config.payment_mode == 'receipt' else 'chapa',
        subscription_plan=subscription,
        amount=amount,
        chapa_tx_ref=tx_ref,
        start_date=start_date,
        end_date=end_date,
        period_type=period_type,
        status=status_value,
        payment_status=payment_status_value,
        assigned_admin=_pick_receipt_admin() if payment_config.payment_mode == 'receipt' else None,
    )

    if not subscription and grades:
        payment.grade.set(grades)
    elif subscription and subscription.grades.exists():
        payment.grade.set(subscription.grades.all())

    # -----------------------
    # Call Chapa API
    # -----------------------
    if payment_config.payment_mode == 'receipt':
        assigned_profile = getattr(payment.assigned_admin, 'subscription_receipt_admin_profile', None)
        serialized_profile = SubscriptionReceiptAdminProfileSerializer(assigned_profile).data if assigned_profile else None
        return Response({
            "payment_mode": "receipt",
            "payment": PaymentSerializer(payment).data,
            "bank_assignment": serialized_profile,
            "bank_accounts": serialized_profile.get("bank_accounts", []) if serialized_profile else [],
            "tx_ref": tx_ref,
        }, status=status.HTTP_200_OK)

    payload = {
        "amount": str(amount),
        "currency": "ETB",
        "email": user.email,
        "first_name": user.first_name or "Customer",
        "last_name": user.last_name or "",
        "tx_ref": tx_ref,
        "return_url": return_url,
    }
    headers = {
        "Authorization": f"Bearer {CHAPA_API_KEY}",
        "Content-Type": "application/json",
    }

    chapa_response = requests.post(CHAPA_INIT_URL, json=payload, headers=headers).json()

    if chapa_response.get("status") == "success":
        return Response({
            "checkout_url": chapa_response["data"]["checkout_url"],
            "tx_ref": tx_ref
        }, status=status.HTTP_200_OK)

    return Response({"error": "Failed to initialize payment"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
def upload_receipt(request):
    serializer = UploadSubscriptionReceiptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if serializer.validated_data.get('payment_id') is None:
        try:
            prepared = _prepare_subscription_payment(request, request.data)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        bank_account_id = serializer.validated_data.get('bank_account_id')
        selected_account = None
        if bank_account_id is not None:
            selected_account = SubscriptionReceiptAdminBankAccount.objects.select_related('profile__user').filter(
                id=bank_account_id,
                is_active=True,
            ).first()
            if not selected_account:
                return Response({'error': 'Invalid bank account selection.'}, status=400)
        else:
            preview_admin = _pick_receipt_admin()
            preview_profile = getattr(preview_admin, 'subscription_receipt_admin_profile', None) if preview_admin else None
            preview_accounts = _get_receipt_accounts(preview_profile)
            if len(preview_accounts) > 1:
                return Response({'error': 'Bank account selection is required.'}, status=400)
            selected_account = preview_accounts[0] if preview_accounts else None

        payment = _create_subscription_receipt_payment(prepared, selected_account=selected_account)
        payment.receipt_file = serializer.validated_data['receipt_file']
        payment.selected_receipt_account = selected_account or payment.selected_receipt_account
        if payment.selected_receipt_account and payment.assigned_admin_id != payment.selected_receipt_account.profile.user_id:
            payment.assigned_admin = payment.selected_receipt_account.profile.user
        payment.receipt_uploaded_at = timezone.now()
        payment.payment_status = 'pending'
        payment.save(update_fields=['receipt_file', 'selected_receipt_account', 'assigned_admin', 'receipt_uploaded_at', 'payment_status'])
        return Response({'message': 'Receipt uploaded successfully.', 'payment': PaymentSerializer(payment).data})

    payment = Payment.objects.filter(id=serializer.validated_data['payment_id'], user=request.user).first()
    if not payment:
        return Response({'error': 'Payment not found.'}, status=404)
    if payment.provider != 'receipt':
        return Response({'error': 'This payment does not accept receipt upload.'}, status=400)
    if payment.payment_status == 'completed':
        return Response({'error': 'Receipt already approved.'}, status=400)
    assigned_profile = getattr(payment.assigned_admin, 'subscription_receipt_admin_profile', None)
    bank_account_id = serializer.validated_data.get('bank_account_id')
    selected_account = None
    if bank_account_id is not None:
        selected_account = SubscriptionReceiptAdminBankAccount.objects.filter(
            id=bank_account_id,
            profile=assigned_profile,
            is_active=True,
        ).first()
        if not selected_account:
            return Response({'error': 'Invalid bank account selection.'}, status=400)
    else:
        accounts = _get_receipt_accounts(assigned_profile)
        if len(accounts) > 1:
            return Response({'error': 'Bank account selection is required.'}, status=400)
        selected_account = accounts[0] if accounts else None
    payment.receipt_file = serializer.validated_data['receipt_file']
    payment.selected_receipt_account = selected_account
    payment.receipt_uploaded_at = timezone.now()
    payment.payment_status = 'pending'
    payment.save(update_fields=['receipt_file', 'selected_receipt_account', 'receipt_uploaded_at', 'payment_status'])
    return Response({'message': 'Receipt uploaded successfully.', 'payment': PaymentSerializer(payment).data})


@api_view(['POST'])
def receipt_admin_login(request):
    serializer = SubscriptionReceiptAdminLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = authenticate(
        username=serializer.validated_data['username'],
        password=serializer.validated_data['password'],
    )
    if not user:
        return Response({'error': 'Invalid credentials'}, status=400)
    if not _is_receipt_manager(user):
        return Response({'error': 'You are not assigned as a receipt manager.'}, status=403)
    tokens = _build_receipt_admin_token(user)
    return Response({
        **tokens,
        'user': {
            'id': user.id,
            'username': user.username,
            'role': 'super' if _is_super_receipt_admin(user) else 'manager',
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assigned_receipts(request):
    if not _is_receipt_manager(request.user):
        return Response({'error': 'Not authorized.'}, status=403)
    queryset = Payment.objects.filter(
        provider='receipt',
    ).select_related('assigned_admin', 'reviewed_by', 'selected_receipt_account', 'user').order_by('-receipt_uploaded_at', '-created_at')
    visible_receipts = queryset if _is_super_receipt_admin(request.user) else queryset.filter(assigned_admin=request.user)
    admin_profiles = SubscriptionReceiptAdminProfile.objects.select_related('user').filter(is_active=True, user__is_active=True).order_by('rotation_order', 'id')
    admin_summaries = []
    for profile in admin_profiles:
        admin_summaries.append({
            'admin_id': profile.user_id,
            'admin_name': profile.user.get_full_name().strip() or profile.user.username,
            'bank_name': profile.bank_name,
            'account_number': profile.account_number,
            **_build_receipt_admin_summary(queryset, admin_user=profile.user),
        })
    return Response({
        'scope': 'all' if _is_super_receipt_admin(request.user) else 'self',
        'payments': PaymentSerializer(visible_receipts, many=True).data,
        'my_summary': _build_receipt_admin_summary(queryset, admin_user=request.user),
        'admin_summaries': admin_summaries if _is_super_receipt_admin(request.user) else [],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def review_receipt(request, payment_id):
    if not _is_receipt_manager(request.user):
        return Response({'error': 'Not authorized.'}, status=403)
    serializer = SubscriptionReceiptReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payment_queryset = Payment.objects.filter(id=payment_id, provider='receipt')
    if not _is_super_receipt_admin(request.user):
        payment_queryset = payment_queryset.filter(assigned_admin=request.user)
    payment = payment_queryset.first()
    if not payment:
        return Response({'error': 'Receipt payment not found.'}, status=404)

    action = serializer.validated_data['action']
    note = serializer.validated_data.get('note', '')

    if action == 'approve' and payment.payment_status == 'completed':
        return Response({'error': 'This receipt is already approved.'}, status=400)
    if action == 'decline' and payment.payment_status == 'failed':
        return Response({'error': 'This receipt is already declined.'}, status=400)

    payment.reviewed_by = request.user
    payment.review_note = note
    payment.reviewed_at = timezone.now()

    if action == 'approve':
        payment.payment_status = 'completed'
        payment.status = 'active' if payment.start_date <= timezone.now() else 'pending'
        _send_receipt_approved_notification(payment.user)
    else:
        payment.payment_status = 'failed'
        _send_receipt_rejected_notification(payment.user)

    payment.save(update_fields=['payment_status', 'status', 'reviewed_by', 'review_note', 'reviewed_at'])
    return Response({
        'message': f'Receipt {action}d successfully.',
        'payment': PaymentSerializer(payment).data,
    })


CHAPA_WEBHOOK_SECRET = settings.CHAPA_WEBHOOK_SECRET  # store in .env

@api_view(['POST'])
@permission_classes([AllowAny])  # no auth, Chapa calls directly
def chapa_webhook(request):
    # Get headers
    sig1 = request.headers.get("Chapa-Signature")
    sig2 = request.headers.get("x-chapa-signature")

    # Compute expected hashes
    body_bytes = request.body  # raw body is required for HMAC
    expected_hash1 = hmac.new(
        CHAPA_WEBHOOK_SECRET.encode(),
        msg=CHAPA_WEBHOOK_SECRET.encode(),  # signed with secret itself
        digestmod=hashlib.sha256
    ).hexdigest()

    expected_hash2 = hmac.new(
        CHAPA_WEBHOOK_SECRET.encode(),
        msg=body_bytes,  # signed with payload
        digestmod=hashlib.sha256
    ).hexdigest()

    # Check signatures
    if not (
        (sig1 and hmac.compare_digest(sig1, expected_hash1)) or
        (sig2 and hmac.compare_digest(sig2, expected_hash2))
    ):
        return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

    # ✅ Signature verified → process event
    tx_ref = request.data.get("tx_ref")
    event_ = request.data.get("event")

    if not tx_ref:
        return Response({"error": "tx_ref missing"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payment = Payment.objects.get(chapa_tx_ref=tx_ref)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

    if event_ == "charge.success" or event_ == "payout.success":
        payment.payment_status = "completed"
        # TODO: activate subscription here
    else:
        payment.payment_status = "failed"

    payment.save()
    return Response({"message": "Webhook processed"}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsVerified])
def get_active_subscriptions(request):
    """
    Return all subscriptions of the authenticated user
    which are paid (payment_status=completed) and not expired.
    """
    user = request.user
    child_id = request.query_params.get('child_id')

    # If child_id is provided, validate parent-child relationship
    if child_id:
        try:
            child_id = int(child_id)
        except ValueError:
            return Response({'error': 'Invalid child_id.'}, status=400)

        is_valid_relation = ParentChild.objects.filter(
            parent=user,
            child_id=child_id,
            status='active'
        ).exists()

        if not is_valid_relation:
            return Response({'error': 'You are not authorized to access this child\'s data.'}, status=403)

        # If valid, use the child as the target user
        try:
            user = CustomUser.objects.get(id=child_id)
            if user.is_verified == False:
                return Response({'error': 'Child user is not verified.'}, status=400)
        except CustomUser.DoesNotExist:
            return Response({'error': 'Child user not found.'}, status=404)    
    now = timezone.now()
    subscriptions = Payment.objects.filter(
        user=user,
        payment_status="completed",
        end_date__gte=now
    ).order_by("start_date")

    serializer = PaymentSerializer(subscriptions, many=True)
    return Response(serializer.data)


