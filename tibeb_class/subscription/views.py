from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import SubscriptionPlan,SubscriptionPlanPricing
from .serializers import SubscriptionPlanSerializer
from rest_framework import status
from decimal import Decimal



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
