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
from .models import ParentChild, SubsectionProgress, User_Grade,UserSubscription
from contents.models import Subsection
from subscription.models import SubscriptionPlan
from contents.models import Grade,Video, Chapter


User = get_user_model()

# Create your views here.
@api_view(['POST'])
def login(request):
        user = get_object_or_404(User, username=request.data['email'])
        if not user.check_password(request.data['password']):
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)
        token, created = Token.objects.get_or_create(user=user)
        serializer = UserSerializer(instance=user)
        return Response({'token': token.key, 'user': serializer.data}, status=status.HTTP_200_OK)
@api_view(['POST'])
def signup(request):
    data = request.data.copy()
    data['username'] = data.get('email')

    grade_ids = data.getlist('grades') if hasattr(data, 'getlist') else data.get('grades', [])
    if isinstance(grade_ids, str):  
        grade_ids = [grade_ids]
    if grade_ids:
        for grade_id in grade_ids:
            if not Grade.objects.filter(id=grade_id).exists():
                return Response({'error': f'Invalid grade ID: {grade_id}'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = UserSerializer(data=data)
    if serializer.is_valid():
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)

        grades = user.grades.all()
        for i, grade in enumerate(grades):
            User_Grade.objects.create(user=user, grade=grade)

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
    grade_ids = child_data.getlist('grades') if hasattr(child_data, 'getlist') else child_data.get('grades', [])
    if isinstance(grade_ids, str):  
        grade_ids = [grade_ids]
    if grade_ids:
        for grade_id in grade_ids:
            if not Grade.objects.filter(id=grade_id).exists():
                return Response({'error': f'Invalid grade ID: {grade_id}'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = UserSerializer(data=child_data)
        if serializer.is_valid():
            child_user = serializer.save()
            ParentChild.objects.create(parent=parent, child=child_user, status='active')
            grades = child_user.grades.all()
            for i, grade in enumerate(grades):
                User_Grade.objects.create(user=child_user, grade=grade)            
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
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from django.shortcuts import get_object_or_404

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_progress(request):
    user = request.user
    video_id = request.data.get('video_id')

    try:
        video = Video.objects.get(id=video_id) 
    except  Video.DoesNotExist:
        return Response({'error': 'video not found'}, status=404)

    progress, created = SubsectionProgress.objects.get_or_create(user=user, video=video)

    watched_seconds = request.data.get('watched_seconds')
    if watched_seconds is not None:
        progress.watched_seconds = int(watched_seconds)

    if video and video.duration:
        video_seconds = video.duration.total_seconds()
        percentage = round((progress.watched_seconds / video_seconds) * 100, 2)
        if percentage >= 100:
            percentage = 100.0
        progress.completed_percentage = percentage
    else:
        percentage = None  # If no video or duration is missing
    progress.save()

    return Response({
        'message': 'Progress updated.',
        'percentage_completed': percentage
    }, status=200)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_progress(request):
    user = request.user
    progress_qs = SubsectionProgress.objects.filter(user=user)

    result = [
        {
            'id': p.id,
            'video_id': p.video.id if p.video else None,
            'watched_seconds': p.watched_seconds,
            'completed_percentage': p.completed_percentage,
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



@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def user_grade(request):
    user = request.user
    user_grades = User_Grade.objects.filter(user=user, is_active=True)
    result = []
    for user_grade in user_grades:
        grade = user_grade.grade
        result.append({
            'id': user_grade.id,
            'grade_id': grade.id,
            'grade_name': grade.name,
            'is_active': user_grade.is_active
        })
    return Response(result, status=200)
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def start_grade(request):
    user = request.user
    grade_id = request.data.get('grade_id')
    if not grade_id:
        return Response({'error': 'Missing grade_id parameter.'}, status=400)
    try:
        grade = Grade.objects.get(id=grade_id)
    except Grade.DoesNotExist:
        return Response({'error': 'Grade not found.'}, status=404)
    user_grade, created = User_Grade.objects.get_or_create(user=user, grade=grade)
    if created:
        user_grade.is_active = True
        user_grade.save()
        return Response({'message': 'Grade started successfully.'}, status=201)
    else:
        return Response({'message': 'Grade already started.'}, status=200)
    
from django.utils.timezone import datetime

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def aggregated_progress_per_grade(request):
    user = request.user

    user_grades = User_Grade.objects.filter(user=user, is_active=True).select_related('grade')
    grade_ids = [ug.grade.id for ug in user_grades]
    grades = Grade.objects.filter(id__in=grade_ids)

    result = []

    for grade in grades:
        videos = Video.objects.filter(subsection__chapter__subject__grade=grade)
        video_ids = list(videos.values_list('id', flat=True))

        progresses = SubsectionProgress.objects.filter(user=user, video_id__in=video_ids)
        progress_map = {p.video_id: p.completed_percentage for p in progresses}

        total_percentage = sum(progress_map.get(video_id, 0) for video_id in video_ids)
        total_videos = len(video_ids)
        watched_videos = len(progresses)

        # Get the latest progress date for sorting
        latest_watch = progresses.order_by('-last_watched_at').first()
        last_watched_at = latest_watch.last_watched_at if latest_watch else None

        average_percentage = round(total_percentage / total_videos, 2) if total_videos > 0 else 0.0

        result.append({
            'grade_id': grade.id,
            'grade_name': grade.name,
            'video_count': total_videos,
            'videos_with_progress': watched_videos,
            'average_percentage_completed': average_percentage,
            'last_watched_at': last_watched_at
        })

    # Sort by last_watched_at (most recent first), None values last
    sorted_result = sorted(
        result,
        key=lambda x: x['last_watched_at'] or datetime.min,
        reverse=True
    )

    return Response({
        'level': 'grade',
        'grades_progress': sorted_result
    }, status=200)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def aggregated_progress_subject_level(request):
    user = request.user
    level = request.query_params.get('level')
    parent_id = request.query_params.get('id')

    if level != 'subject':
        return Response({'error': 'Only subject-level aggregation is implemented in this version.'}, status=400)

    if not parent_id:
        return Response({'error': 'Missing id parameter.'}, status=400)

    try:
        parent_id = int(parent_id)
    except ValueError:
        return Response({'error': 'ID must be an integer.'}, status=400)

    subjects = Subject.objects.filter(grade_id=parent_id)

    result = []

    for subject in subjects:
        videos = Video.objects.filter(subsection__chapter__subject=subject)
        video_ids = list(videos.values_list('id', flat=True))

        progresses = SubsectionProgress.objects.filter(user=user, video_id__in=video_ids)
        progress_map = {p.video_id: p.completed_percentage for p in progresses}

        total_percentage = sum(progress_map.get(video_id, 0) for video_id in video_ids)
        total_videos = len(video_ids)
        watched_videos = len(progresses)

        average_percentage = round(total_percentage / total_videos, 2) if total_videos > 0 else 0.0

        result.append({
            'subject_id': subject.id,
            'subject_name': subject.name,
            'video_count': total_videos,
            'videos_with_progress': watched_videos,
            'average_percentage_completed': average_percentage
        })

    return Response({
        'grade_id': parent_id,
        'level': 'subject',
        'subject_progress': result
    }, status=200)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def aggregated_progress_chapter_level(request):
    user = request.user
    level = request.query_params.get('level')
    parent_id = request.query_params.get('id')

    if level != 'chapter':
        return Response({'error': 'Only chapter-level aggregation is implemented in this version.'}, status=400)

    if not parent_id:
        return Response({'error': 'Missing id parameter.'}, status=400)

    try:
        parent_id = int(parent_id)
    except ValueError:
        return Response({'error': 'ID must be an integer.'}, status=400)

    chapters = Chapter.objects.filter(subject_id=parent_id).prefetch_related('subsections__videos')

    result = []

    for chapter in chapters:
        videos = Video.objects.filter(subsection__chapter=chapter)
        all_video_ids = list(videos.values_list('id', flat=True))

        # Get progress records for the user's videos in this chapter
        progresses = SubsectionProgress.objects.filter(user=user, video_id__in=all_video_ids)
        progress_map = {p.video_id: p.completed_percentage for p in progresses}

        # Sum up progress for all videos, including 0 for unwatched
        total_percentage = sum(progress_map.get(video_id, 0) for video_id in all_video_ids)
        video_count = len(all_video_ids)

        average_percentage = round(total_percentage / video_count, 2) if video_count > 0 else 0.0

        result.append({
            'chapter_id': chapter.id,
            'chapter_title': chapter.title,
            'video_count': video_count,
            'videos_with_progress': len(progresses),
            'average_percentage_completed': average_percentage
        })

    return Response({
        'subject_id': parent_id,
        'level': 'chapter',
        'chapter_progress': result
    }, status=200)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def aggregated_progress_subsection_level(request):
    user = request.user
    level = request.query_params.get('level')
    parent_id = request.query_params.get('id')

    if level != 'subsection':
        return Response({'error': 'Only subsection-level aggregation is implemented in this version.'}, status=400)

    if not parent_id:
        return Response({'error': 'Missing id parameter.'}, status=400)

    try:
        parent_id = int(parent_id)
    except ValueError:
        return Response({'error': 'ID must be an integer.'}, status=400)

    subsections = Subsection.objects.filter(chapter_id=parent_id)

    result = []

    for subsection in subsections:
        videos = Video.objects.filter(subsection=subsection)
        video_ids = list(videos.values_list('id', flat=True))

        progresses = SubsectionProgress.objects.filter(user=user, video_id__in=video_ids)
        progress_map = {p.video_id: p.completed_percentage for p in progresses}

        total_percentage = sum(progress_map.get(video_id, 0) for video_id in video_ids)
        total_videos = len(video_ids)
        watched_videos = len(progresses)

        average_percentage = round(total_percentage / total_videos, 2) if total_videos > 0 else 0.0

        result.append({
            'subsection_id': subsection.id,
            'subsection_title': subsection.title,
            'video_count': total_videos,
            'videos_with_progress': watched_videos,
            'average_percentage_completed': average_percentage
        })

    return Response({
        'chapter_id': parent_id,
        'level': 'subsection',
        'subsection_progress': result
    }, status=200)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def subsection_progress_summary(request):
    user = request.user
    subsection_id = request.query_params.get('subsection_id')

    if not subsection_id:
        return Response({'error': 'Missing subsection_id parameter.'}, status=400)

    try:
        subsection = Subsection.objects.get(id=subsection_id)
    except Subsection.DoesNotExist:
        return Response({'error': 'Subsection not found.'}, status=404)

    videos = Video.objects.filter(subsection=subsection)
    video_ids = list(videos.values_list('id', flat=True))

    progresses = SubsectionProgress.objects.filter(user=user, video_id__in=video_ids)
    progress_map = {p.video_id: p.completed_percentage for p in progresses}

    total_percentage = sum(progress_map.get(video_id, 0) for video_id in video_ids)
    total_videos = len(video_ids)
    videos_with_progress = len(progresses)
    average_percentage = round(total_percentage / total_videos, 2) if total_videos > 0 else 0.0

    return Response({
        'subsection_id': subsection.id,
        'subsection_title': subsection.title,
        'video_count': total_videos,
        'videos_with_progress': videos_with_progress,
        'average_percentage_completed': average_percentage
    }, status=200)




    
