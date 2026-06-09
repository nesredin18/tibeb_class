from datetime import timedelta
import json
import logging
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
from .receipt_storage import build_receipt_url, save_subscription_receipt_locally
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
from urllib.parse import urljoin


logger = logging.getLogger(__name__)

RECEIPT_VERIFIER_ENABLED = getattr(settings, "SUBSCRIPTION_RECEIPT_VERIFIER_ENABLED", False)
RECEIPT_VERIFIER_BASE_URL = (getattr(settings, "SUBSCRIPTION_RECEIPT_VERIFIER_BASE_URL", "") or "").rstrip("/")
RECEIPT_VERIFIER_API_KEY = getattr(settings, "SUBSCRIPTION_RECEIPT_VERIFIER_API_KEY", "")
RECEIPT_VERIFIER_TIMEOUT = int(getattr(settings, "SUBSCRIPTION_RECEIPT_VERIFIER_TIMEOUT", 30))
RECEIPT_VERIFIER_WEBHOOK_SECRET = getattr(settings, "SUBSCRIPTION_RECEIPT_VERIFIER_WEBHOOK_SECRET", "")

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


def _append_review_note(existing_note, new_note):
    existing = (existing_note or "").strip()
    extra = (new_note or "").strip()
    if not extra:
        return existing
    return f"{existing}\n\n{extra}" if existing else extra


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


def _send_receipt_rejected_notification(user, reason=""):
    target, contact_type = _get_user_notification_contact(user)
    if not target:
        return
    reason_text = (reason or "").strip()
    reason_html = f"<p style=\"color:#4b5563;font-size:14px;margin:0 0 24px;\"><strong>Reason:</strong> {reason_text}</p>" if reason_text else ""
    reason_sms = f" Reason: {reason_text}" if reason_text else ""
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
              {reason_html}
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
        send_sms_otp(target, f"Your Tibeb Class receipt payment was rejected. Please upload a valid receipt or contact support.{reason_sms}")


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


def _build_receipt_verifier_headers():
    headers = {
        "Accept": "application/json",
    }
    if RECEIPT_VERIFIER_API_KEY:
        headers["X-EthioVerify-Key"] = RECEIPT_VERIFIER_API_KEY
    return headers


def _build_receipt_verifier_webhook_url():
    base = (getattr(settings, "BACKEND_URL", "") or "").rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/subscription-plans"):
        base = base[: -len("/api/subscription-plans")]
    elif base.endswith("/api/subscription-plans/"):
        base = base[: -len("/api/subscription-plans/")]
    return f"{base}/api/subscription-plans/receipt-verifier-webhook/"


def _get_receipt_absolute_url(payment):
    if not payment.receipt_file:
        return ""
    return build_receipt_url(payment.receipt_file.name) or ""


def _extract_verifier_data(payload):
    if isinstance(payload, dict):
        for key in ("data", "result", "payment", "record"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
    return payload if isinstance(payload, dict) else {}


def _extract_verifier_success(payload):
    data = _extract_verifier_data(payload)
    candidates = []
    if isinstance(payload, dict):
        candidates.extend([payload.get("success"), payload.get("verified"), payload.get("ok")])
    candidates.extend([data.get("success"), data.get("verified"), data.get("ok")])
    for candidate in candidates:
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, (int, float)):
            return bool(candidate)
        if isinstance(candidate, str):
            normalized = candidate.strip().lower()
            if normalized in {"true", "1", "yes", "verified", "approved", "success"}:
                return True
            if normalized in {"false", "0", "no", "failed", "error"}:
                return False
    return None


def _extract_verifier_status(payload):
    data = _extract_verifier_data(payload)
    candidates = [
        payload.get("status") if isinstance(payload, dict) else None,
        payload.get("verification_status") if isinstance(payload, dict) else None,
        payload.get("state") if isinstance(payload, dict) else None,
        payload.get("event") if isinstance(payload, dict) else None,
        data.get("status"),
        data.get("verification_status"),
        data.get("state"),
        data.get("result"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate).strip().lower()
    return ""


def _extract_verifier_reference(payload):
    data = _extract_verifier_data(payload)
    candidates = [
        payload.get("merchant_order_id") if isinstance(payload, dict) else None,
        payload.get("merchant_request_id") if isinstance(payload, dict) else None,
        payload.get("reference") if isinstance(payload, dict) else None,
        data.get("merchant_order_id"),
        data.get("merchant_request_id"),
        data.get("reference"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate).strip()
    return ""


def _extract_verifier_note(payload):
    data = _extract_verifier_data(payload)
    candidates = [
        payload.get("reason") if isinstance(payload, dict) else None,
        payload.get("message") if isinstance(payload, dict) else None,
        payload.get("detail") if isinstance(payload, dict) else None,
        payload.get("error") if isinstance(payload, dict) else None,
        payload.get("note") if isinstance(payload, dict) else None,
        data.get("reason"),
        data.get("message"),
        data.get("detail"),
        data.get("error"),
        data.get("note"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate).strip()
    return ""


def _is_verifier_approved_status(status_value):
    return status_value in {"verified", "approved", "success", "completed", "matched", "payment.verified"}


def _is_verifier_rejected_status(status_value):
    return status_value in {"rejected", "failed", "declined", "invalid", "manual-rejected", "manual_rejected", "manual_failed", "payment.failed_after_manual_check"}


def _is_verifier_pending_status(status_value):
    return status_value in {"pending", "processing", "review", "manual-review", "manual_review", "queued", "verifying"}


def _build_receipt_verifier_verify_url():
    base = RECEIPT_VERIFIER_BASE_URL.rstrip("/")
    if base.endswith("/api"):
        return f"{base}/gateway/verify-async/"
    return f"{base}/api/gateway/verify-async/"


def _stable_json_dumps(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_verifier_bank(bank_name):
    value = (bank_name or "").strip().lower()
    if not value:
        return ""
    mappings = {
        "commercial bank of ethiopia": "cbe",
        "cbe": "cbe",
        "bank of abyssinia": "abyssinia",
        "abyssinia": "abyssinia",
        "cbe birr": "cbe_birr",
        "cbebirr": "cbe_birr",
        "telebirr": "telebirr",
        "dashen": "dashen",
        "dashen bank": "dashen",
        "m-pesa": "mpesa",
        "mpesa": "mpesa",
    }
    return mappings.get(value, "")


def _build_receipt_verifier_request_data(payment):
    selected_account = payment.selected_receipt_account
    bank_code = _normalize_verifier_bank(getattr(selected_account, "bank_name", ""))
    receiver_name = (
        (getattr(selected_account, "account_holder_name", "") or "").strip()
        or (payment.assigned_admin.get_full_name().strip() if payment.assigned_admin else "")
        or (payment.assigned_admin.username if payment.assigned_admin else "")
    )

    payload = {
        "amount": str(payment.amount),
        "receiver_name": receiver_name,
        "merchant_order_id": payment.chapa_tx_ref,
    }
    if bank_code:
        payload["bank"] = bank_code

    account_number = (getattr(selected_account, "account_number", "") or "").strip()
    if bank_code in {"cbe", "abyssinia"} and account_number:
        payload["account_suffix"] = account_number
    if bank_code == "cbe_birr" and account_number:
        payload["phone_number"] = account_number
    return payload


def _approve_receipt_payment(payment, *, reviewer=None, note="", source="manual"):
    if payment.payment_status == 'completed':
        logger.info(
            "Subscription receipt approval skipped. payment_id=%s source=%s reviewer_id=%s status=%s",
            payment.id,
            source,
            getattr(reviewer, "id", None),
            payment.payment_status,
        )
        return False
    payment.reviewed_by = reviewer
    payment.review_note = _append_review_note(payment.review_note, note or f"Receipt approved via {source}.")
    payment.reviewed_at = timezone.now()
    payment.payment_status = 'completed'
    payment.status = 'active' if payment.start_date <= timezone.now() else 'pending'
    payment.save(update_fields=['payment_status', 'status', 'reviewed_by', 'review_note', 'reviewed_at'])
    logger.info(
        "Subscription receipt approved. payment_id=%s source=%s reviewer_id=%s final_status=%s payment_status=%s",
        payment.id,
        source,
        getattr(reviewer, "id", None),
        payment.status,
        payment.payment_status,
    )
    _send_receipt_approved_notification(payment.user)
    return True


def _decline_receipt_payment(payment, *, reviewer=None, note="", source="manual"):
    if payment.payment_status == 'failed':
        logger.info(
            "Subscription receipt rejection skipped. payment_id=%s source=%s reviewer_id=%s status=%s",
            payment.id,
            source,
            getattr(reviewer, "id", None),
            payment.payment_status,
        )
        return False
    payment.reviewed_by = reviewer
    payment.review_note = _append_review_note(payment.review_note, note or f"Receipt rejected via {source}.")
    payment.reviewed_at = timezone.now()
    payment.payment_status = 'failed'
    payment.save(update_fields=['payment_status', 'reviewed_by', 'review_note', 'reviewed_at'])
    logger.info(
        "Subscription receipt rejected. payment_id=%s source=%s reviewer_id=%s payment_status=%s",
        payment.id,
        source,
        getattr(reviewer, "id", None),
        payment.payment_status,
    )
    _send_receipt_rejected_notification(payment.user, reason=note)
    return True


def _trigger_receipt_auto_verification(payment, receipt_file=None):
    if not RECEIPT_VERIFIER_ENABLED or not RECEIPT_VERIFIER_BASE_URL or not RECEIPT_VERIFIER_API_KEY:
        logger.info(
            "Subscription receipt verifier skipped. payment_id=%s enabled=%s base_url_set=%s api_key_set=%s",
            getattr(payment, "id", None),
            RECEIPT_VERIFIER_ENABLED,
            bool(RECEIPT_VERIFIER_BASE_URL),
            bool(RECEIPT_VERIFIER_API_KEY),
        )
        return {"attempted": False, "reason": "Verifier is not configured."}

    verify_url = _build_receipt_verifier_verify_url()
    payload = _build_receipt_verifier_request_data(payment)
    logger.info(
        "Subscription receipt verifier request starting. payment_id=%s verify_url=%s payload=%s has_receipt=%s webhook_url=%s",
        payment.id,
        verify_url,
        payload,
        bool(payment.receipt_file),
        _build_receipt_verifier_webhook_url(),
    )

    files = None
    opened_remote_receipt = False
    try:
        if receipt_file:
            try:
                receipt_file.seek(0)
            except Exception:
                pass
            file_handle = getattr(receipt_file, "file", receipt_file)
            files = {
                "receipt": (
                    getattr(receipt_file, "name", payment.receipt_file.name.split("/")[-1] if payment.receipt_file else "receipt"),
                    file_handle,
                    getattr(receipt_file, "content_type", None) or "application/octet-stream",
                )
            }
            logger.info("Subscription receipt verifier using uploaded file object. payment_id=%s", payment.id)
        elif payment.receipt_file:
            payment.receipt_file.open("rb")
            opened_remote_receipt = True
            file_handle = payment.receipt_file.file
            files = {
                "receipt": (
                    payment.receipt_file.name.split("/")[-1],
                    file_handle,
                    getattr(file_handle, "content_type", None) or "application/octet-stream",
                )
            }

        response = requests.post(
            verify_url,
            headers=_build_receipt_verifier_headers(),
            data=payload,
            files=files,
            timeout=RECEIPT_VERIFIER_TIMEOUT,
        )
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {"raw": response.text}

        success_value = _extract_verifier_success(response_payload)
        status_value = _extract_verifier_status(response_payload)
        note = _extract_verifier_note(response_payload) or f"Verifier response status: {status_value or response.status_code}."
        logger.info(
            "Receipt async verification response. payment_id=%s status_code=%s verifier_success=%s verifier_status=%s payload=%s",
            payment.id,
            response.status_code,
            success_value,
            status_value,
            response_payload,
        )

        if response.ok and success_value is True and _is_verifier_approved_status(status_value):
            _approve_receipt_payment(
                payment,
                note=f"Auto-approved by EthioVerify. {note}".strip(),
                source="ethioverify",
            )
            return {"attempted": True, "approved": True, "payload": response_payload}

        if response.ok and (success_value is False or _is_verifier_pending_status(status_value) or not status_value):
            payment.review_note = _append_review_note(payment.review_note, f"EthioVerify pending: {note}")
            payment.save(update_fields=["review_note"])
            return {"attempted": True, "approved": False, "payload": response_payload}

        payment.review_note = _append_review_note(payment.review_note, f"EthioVerify did not auto-approve: {note}")
        payment.save(update_fields=["review_note"])
        return {"attempted": True, "approved": False, "payload": response_payload}
    except requests.RequestException as exc:
        logger.warning("Receipt auto verification request failed. payment_id=%s error=%s", payment.id, exc)
        payment.review_note = _append_review_note(payment.review_note, f"EthioVerify request failed: {exc}")
        payment.save(update_fields=["review_note"])
        return {"attempted": True, "approved": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("Receipt auto verification response handling failed. payment_id=%s", payment.id)
        payment.review_note = _append_review_note(payment.review_note, f"EthioVerify response handling failed: {exc}")
        payment.save(update_fields=["review_note"])
        return {"attempted": True, "approved": False, "error": str(exc)}
    finally:
        if opened_remote_receipt and payment.receipt_file:
            payment.receipt_file.close()


def _is_valid_receipt_verifier_webhook(request):
    signature = (
        (request.headers.get("X-EthioVerify-Signature") or "").strip()
        or (request.headers.get("x-ethioverify-signature") or "").strip()
    )
    if not RECEIPT_VERIFIER_WEBHOOK_SECRET or not signature:
        return False

    payload = request.data if isinstance(request.data, (dict, list)) else {}
    serialized = _stable_json_dumps(payload)
    expected = hmac.new(
        RECEIPT_VERIFIER_WEBHOOK_SECRET.encode(),
        msg=serialized.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    accepted = {expected, f"sha256={expected}"}
    return any(hmac.compare_digest(signature, candidate) for candidate in accepted)


def _find_receipt_payment_for_webhook(payload):
    reference = _extract_verifier_reference(payload)
    data = _extract_verifier_data(payload)
    payment_id = None
    for candidate in (
        payload.get("payment_id") if isinstance(payload, dict) else None,
        data.get("payment_id"),
    ):
        if candidate not in (None, ""):
            payment_id = str(candidate).strip()
            break

    payment = None
    if payment_id and payment_id.isdigit():
        payment = Payment.objects.filter(id=int(payment_id), provider="receipt").first()
    if payment is None and reference:
        payment = Payment.objects.filter(chapa_tx_ref=reference, provider="receipt").first()
    return payment


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
    logger.info(
        "Subscription receipt upload called. user_id=%s payment_id=%s bank_account_id=%s keys=%s",
        getattr(request.user, "id", None),
        request.data.get("payment_id"),
        request.data.get("bank_account_id"),
        sorted(list(request.data.keys())),
    )
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
        receipt_file = serializer.validated_data['receipt_file']
        payment.receipt_file.name = save_subscription_receipt_locally(receipt_file)
        payment.selected_receipt_account = selected_account or payment.selected_receipt_account
        if payment.selected_receipt_account and payment.assigned_admin_id != payment.selected_receipt_account.profile.user_id:
            payment.assigned_admin = payment.selected_receipt_account.profile.user
        payment.receipt_uploaded_at = timezone.now()
        payment.payment_status = 'pending'
        payment.save(update_fields=['receipt_file', 'selected_receipt_account', 'assigned_admin', 'receipt_uploaded_at', 'payment_status'])
        verification_result = _trigger_receipt_auto_verification(payment, receipt_file=receipt_file)
        logger.info(
            "Subscription receipt upload finished for new payment. payment_id=%s verification_result=%s final_status=%s",
            payment.id,
            verification_result,
            payment.payment_status,
        )
        message = 'Receipt uploaded successfully.'
        if verification_result.get("approved"):
            message = 'Receipt uploaded and approved automatically.'
        return Response({'message': message, 'payment': PaymentSerializer(payment).data})

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
    receipt_file = serializer.validated_data['receipt_file']
    payment.receipt_file.name = save_subscription_receipt_locally(receipt_file)
    payment.selected_receipt_account = selected_account
    payment.receipt_uploaded_at = timezone.now()
    payment.payment_status = 'pending'
    payment.save(update_fields=['receipt_file', 'selected_receipt_account', 'receipt_uploaded_at', 'payment_status'])
    verification_result = _trigger_receipt_auto_verification(payment, receipt_file=receipt_file)
    logger.info(
        "Subscription receipt upload finished for existing payment. payment_id=%s verification_result=%s final_status=%s",
        payment.id,
        verification_result,
        payment.payment_status,
    )
    message = 'Receipt uploaded successfully.'
    if verification_result.get("approved"):
        message = 'Receipt uploaded and approved automatically.'
    return Response({'message': message, 'payment': PaymentSerializer(payment).data})


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
    logger.info(
        "Subscription manual receipt review requested. admin_id=%s payment_id=%s action=%s note_present=%s current_status=%s",
        request.user.id,
        payment.id,
        action,
        bool(note),
        payment.payment_status,
    )

    if action == 'approve' and payment.payment_status == 'completed':
        return Response({'error': 'This receipt is already approved.'}, status=400)
    if action == 'decline' and payment.payment_status == 'failed':
        return Response({'error': 'This receipt is already declined.'}, status=400)

    if action == 'approve':
        _approve_receipt_payment(payment, reviewer=request.user, note=note, source="receipt-admin")
    else:
        _decline_receipt_payment(payment, reviewer=request.user, note=note, source="receipt-admin")
    logger.info(
        "Subscription manual receipt review completed. admin_id=%s payment_id=%s action=%s final_status=%s",
        request.user.id,
        payment.id,
        action,
        payment.payment_status,
    )
    return Response({
        'message': f'Receipt {action}d successfully.',
        'payment': PaymentSerializer(payment).data,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def receipt_verifier_webhook(request):
    if not _is_valid_receipt_verifier_webhook(request):
        logger.warning(
            "Subscription receipt verifier webhook rejected due to invalid credentials. headers=%s",
            {
                "X-EthioVerify-Key": request.headers.get("X-EthioVerify-Key"),
                "X-EthioVerify-Event": request.headers.get("X-EthioVerify-Event"),
                "X-EthioVerify-Signature": request.headers.get("X-EthioVerify-Signature"),
                "X-Webhook-Secret": request.headers.get("X-Webhook-Secret"),
                "Authorization": request.headers.get("Authorization"),
            },
        )
        return Response({'error': 'Invalid webhook credentials.'}, status=403)

    payload = request.data if isinstance(request.data, dict) else {}
    logger.info("Subscription receipt verifier webhook accepted. payload=%s", payload)
    payment = _find_receipt_payment_for_webhook(payload)
    if not payment:
        logger.warning("Receipt verifier webhook could not match payment. payload=%s", payload)
        return Response({'error': 'Receipt payment not found.'}, status=404)

    status_value = _extract_verifier_status(payload)
    note = _extract_verifier_note(payload)
    logger.info(
        "Receipt verifier webhook received. payment_id=%s verifier_status=%s payload=%s",
        payment.id,
        status_value,
        payload,
    )

    if _is_verifier_approved_status(status_value):
        changed = _approve_receipt_payment(
            payment,
            note=_append_review_note("", note or "Approved by EthioVerify webhook."),
            source="ethioverify-webhook",
        )
        return Response({
            'message': 'Receipt marked as approved.' if changed else 'Receipt was already approved.',
            'payment': PaymentSerializer(payment).data,
        })

    if _is_verifier_rejected_status(status_value):
        changed = _decline_receipt_payment(
            payment,
            note=note or "Rejected by EthioVerify webhook.",
            source="ethioverify-webhook",
        )
        return Response({
            'message': 'Receipt marked as rejected.' if changed else 'Receipt was already rejected.',
            'payment': PaymentSerializer(payment).data,
        })

    payment.review_note = _append_review_note(payment.review_note, note or f"EthioVerify webhook status received: {status_value or 'pending'}.")
    payment.save(update_fields=['review_note'])
    return Response({
        'message': 'Receipt remains pending manual review.',
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


