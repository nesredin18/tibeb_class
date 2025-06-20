from datetime import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .serializers import UserSerializer
from rest_framework.authtoken.models import Token
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .models import ParentChild, SubsectionProgress,UserSubscription
from contents.models import Subsection
from subscription.models import SubscriptionPlan
from contents.models import Grade


User = get_user_model()

# Create your views here.
@api_view(['POST'])
def login(request):
        user = get_object_or_404(User, username=request.data['username'])
        if not user.check_password(request.data['password']):
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)
        token, created = Token.objects.get_or_create(user=user)
        serializer = UserSerializer(instance=user)
        return Response({'token': token.key, 'user': serializer.data}, status=status.HTTP_200_OK)
@api_view(['POST'])
def signup(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        token = Token.objects.create(user=user)
        return Response({'token': token.key, 'user': serializer.data}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def signupforchild(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        token = Token.objects.create(user=user)
        return Response({'token': token.key, 'user': serializer.data}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def test(request):
        
        return Response("passed for {}".format(request.user.username), status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_child_account(request):
    parent = request.user
    if parent.role != 'parent':
        return Response({'error': 'Only parents can add children.'}, status=403)

    child_type = request.data.get('child_type')

    # ✅ Case 1: Create new child
    if child_type == 'new':
        child_data = request.data.get('child')
        if not child_data:
            return Response({'error': 'Child data is required.'}, status=400)

        child_data['role'] = 'student'  # enforce role
        serializer = UserSerializer(data=child_data)
        if serializer.is_valid():
            child_user = serializer.save()
            ParentChild.objects.create(parent=parent, child=child_user, status='active')
            return Response({'message': 'Child account created and linked successfully.'}, status=201)
        return Response(serializer.errors, status=400)

    # ✅ Case 2: Link existing student
    elif child_type == 'existing':
        username = request.data.get('child_username')
        if not username:
            return Response({'error': 'Child username is required.'}, status=400)

        try:
            child_user = User.objects.get(username=username, role='student')
            # Prevent duplicate
            relation, created = ParentChild.objects.get_or_create(parent=parent, child=child_user)

            if not created:
                return Response({'message': f'Relation already exists with status: {relation.status}'}, status=200)

            # If new relation, set to pending
            relation.status = 'pending'
            relation.save()
            return Response({'message': 'Child link request sent (pending approval).'}, status=200)

        except User.DoesNotExist:
            return Response({'error': 'Student not found.'}, status=404)

    return Response({'error': 'Invalid child_type. Use "new" or "existing".'}, status=400)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def respond_to_parent_request(request):
    if request.user.role != 'student':
        return Response({'error': 'Only students can respond to requests.'}, status=403)

    parent_id = request.data.get('parent_id')
    decision = request.data.get('decision')  # 'accept' or 'reject'

    try:
        relation = ParentChild.objects.get(parent_id=parent_id, child=request.user)
        if decision == 'accept':
            relation.status = 'active'
        elif decision == 'reject':
            relation.status = 'rejected'
        else:
            return Response({'error': 'Invalid decision.'}, status=400)

        relation.save()
        return Response({'message': f'Request {relation.status}.'}, status=200)

    except ParentChild.DoesNotExist:
        return Response({'error': 'No such request found.'}, status=404)
    
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_info(request):
    user = request.user
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role
    }, status=200)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_pending_requests(request):
    if request.user.role != 'student':
        return Response({'error': 'Only students can view parent requests.'}, status=403)

    pending_requests = request.user.parents.filter(status='pending')
    
    result = [
        {
            'relation_id': r.id,
            'parent_id': r.parent.id,
            'parent_username': r.parent.username,
            'status': r.status
        }
        for r in pending_requests
    ]
    return Response(result, status=200)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_accepted_requests(request):
    if request.user.role != 'student':
        return Response({'error': 'Only students can view parent requests.'}, status=403)

    accepted_requests = request.user.parents.filter(status='active')

    result = [
        {
            'relation_id': r.id,
            'parent_id': r.parent.id,
            'parent_username': r.parent.username,
            'status': r.status
        }
        for r in accepted_requests
    ]
    return Response(result, status=200)
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_progress(request):
    user = request.user
    subsection_id = request.data.get('subsection_id')

    try:
        subsection = Subsection.objects.get(id=subsection_id)
    except Subsection.DoesNotExist:
        return Response({'error': 'Subsection not found'}, status=404)

    progress, created = SubsectionProgress.objects.get_or_create(user=user, subsection=subsection)

    progress.watched_seconds = request.data.get('watched_seconds', progress.watched_seconds)
    progress.completed = request.data.get('completed', progress.completed)
    progress.save()

    return Response({'message': 'Progress updated.'}, status=200)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_progress(request):
    user = request.user
    progress_qs = SubsectionProgress.objects.filter(user=user)

    result = [
        {
            'subsection_id': p.subsection.id,
            'subsection_title': p.subsection.title,
            'watched_seconds': p.watched_seconds,
            'completed': p.completed,
            'last_watched_at': p.last_watched_at
        }
        for p in progress_qs
    ]

    return Response(result, status=200)
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_user_subscription(request):
    user = request.user
    plan_id = request.data.get('subscription_plan_id')
    grade_id = request.data.get('grade_id')

    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
        grade = Grade.objects.get(id=grade_id)
    except (SubscriptionPlan.DoesNotExist, Grade.DoesNotExist):
        return Response({'error': 'Invalid plan or grade'}, status=404)

    new_subscription = UserSubscription.objects.create(
        user=user,
        subscription_plan=plan,
        grade=grade
    )

    return Response({
        'message': 'Subscription created',
        'start_date': new_subscription.start_date,
        'end_date': new_subscription.end_date,
        'grade': grade.name
    }, status=201)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_active_subscription(request):
    user = request.user
    today = timezone.now().date()

    active = UserSubscription.objects.filter(user=user, is_active=True, end_date__gte=today).first()

    if not active:
        return Response({'message': 'No active subscription'}, status=404)

    return Response({
        'plan': active.subscription_plan.name,
        'grade': active.grade.name if active.grade else None,
        'start_date': active.start_date,
        'end_date': active.end_date
    }, status=200)


    
