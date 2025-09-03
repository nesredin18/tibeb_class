from datetime import timedelta
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from contents.models import Grade
from .models import Payment, SubscriptionPlan,SubscriptionPlanPricing
from .serializers import PaymentInitSerializer, SubscriptionPlanSerializer
from rest_framework import status
from decimal import Decimal
import uuid,requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Payment
import hmac
import hashlib
from django.conf import settings






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



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initialize_payment(request):
    subscription_id = request.data.get("subscription_id")
    duration = request.data.get("duration")
    period_type = request.data.get("period_type")
    grades = request.data.get("grades", [])
    return_url = request.data.get("return_url")  # ✅ comes from frontend
  # list of grade ids

    tx_ref = str(uuid.uuid4())
    user = request.user

    amount = None
    subscription = None
    start_date = timezone.now()
    end_date = None
    if not return_url:
        return_url = DEFAULT_RETURN_URL
    # Case 1: Existing subscription plan
    if subscription_id:
        try:
            subscription = SubscriptionPlan.objects.get(id=subscription_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Invalid subscription plan"}, status=status.HTTP_400_BAD_REQUEST)

        amount = subscription.price
        if subscription.duration and subscription.period_type == "monthly":
            end_date = start_date + timedelta(days=30 * subscription.duration)
        elif subscription.duration and subscription.period_type == "yearly":
            end_date = start_date + timedelta(days=365 * subscription.duration)

    # Case 2: Custom subscription (duration + grades + period_type)
    else:
        if not duration or not period_type or not grades:
            return Response(
                {"error": "duration, period_type, and grades are required for custom plan"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ensure duration is an int
        try:
            duration = int(duration)
        except ValueError:
            return Response({"error": "Duration must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        total_price = Decimal('0.00')
        grade_prices = []

        # if duration is more than 12 months, automatically treat as yearly
        if duration > 12:
            period_type = "yearly"

        grade_objs = Grade.objects.filter(id__in=grades)

        if not grade_objs.exists():
            return Response(
                {"error": "Invalid grades provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ensure all provided grade IDs exist
        if grade_objs.count() != len(grades):
            missing = set(grades) - set(grade_objs.values_list("id", flat=True))
            return Response(
                {"error": f"Some grades were not found: {list(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        for grade in grade_objs:
            try:
                pricing = SubscriptionPlanPricing.objects.get(
                    grade=grade,
                    period_type=period_type
                )
            except SubscriptionPlanPricing.DoesNotExist:
                return Response(
                    {"error": f"No pricing for grade {grade.name} and {period_type}"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # base price per grade
            total_price_grade = pricing.price * Decimal(duration)

            # calculate discount amount
            discount_amount = total_price_grade * (pricing.discount / Decimal('100'))
            total_price_grade -= discount_amount
            total_price += total_price_grade

            grade_prices.append({
                "grade_id": grade.id,
                "base_price": float(pricing.price),
                "discount": float(pricing.discount),
                "discounted_price_per_period": float(discount_amount),
                "total_price_for_duration": float(total_price_grade)
            })

        amount = round(float(total_price), 2)

        # Calculate end_date
        if period_type == "monthly":
            end_date = start_date + timedelta(days=30 * duration)
        elif period_type == "yearly":
            end_date = start_date + timedelta(days=365 * duration)
        else:
            return Response(
                {"error": "Invalid period type"},
                status=status.HTTP_400_BAD_REQUEST
            )
    # Create pending payment
    payment = Payment.objects.create(
        user=user,
        subscription_plan=subscription,
        amount=amount,
        chapa_tx_ref=tx_ref,
        start_date=start_date,
        end_date=end_date,
        period_type=period_type
    )

    if not subscription and grades:  # attach grades if custom
        payment.grade.set(grades)

    # Call Chapa API
    payload = {
        "amount": str(amount),
        "currency": "ETB",
        "email": user.email,
        "first_name": user.first_name or "Customer",
        "last_name": user.last_name or "",
        "tx_ref": tx_ref,
        "return_url": return_url    }

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

    error_message = "Failed to initialize payment"
    return Response(
        {"error": error_message},  # include raw for debugging if needed
        status=status.HTTP_400_BAD_REQUEST
    )


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
        payment.status = "completed"
        # TODO: activate subscription here
    else:
        payment.status = "failed"

    payment.save()
    return Response({"message": "Webhook processed"}, status=status.HTTP_200_OK)



