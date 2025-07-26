from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .serializers import UserSerializer, UserUpdateSerializer
from rest_framework.authtoken.models import Token
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .models import BookProgress, ExerciseProgress, ParentChild, User_Grade,UserSubscription, VideoProgress,BookProgress
from contents.models import Book, Exercise, Subject, Subsection
from subscription.models import SubscriptionPlan
from contents.models import Grade,Video, Chapter
from django.utils.timezone import make_aware
from datetime import datetime
from django.db.models import Q
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings




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

@api_view(['GET'])
def verify_email(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({'error': 'Invalid verification link.'}, status=status.HTTP_400_BAD_REQUEST)

    if default_token_generator.check_token(user, token):
        if not user.is_verified:
            user.is_verified = True
            user.save(update_fields=["is_verified"])
        return Response({'message': 'Email successfully verified.'}, status=status.HTTP_200_OK)
    else:
        return Response({'error': 'Verification link is invalid or expired.'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def resend_verification_email(request):
    user = request.user

    if user.is_verified:  # Assuming you have a boolean field `is_verified` on your CustomUser model
        return Response({'message': 'User is already verified.'}, status=status.HTTP_400_BAD_REQUEST)

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    domain = settings.FRONTEND_URL  # e.g., from settings.FRONTEND_URL

    verification_link = f"{domain}/verify-email/{uid}/{token}/"

    # Optional: you can import and use the `render_verification_email_html` you created before
    email_body = f"Click the link to verify your email: {verification_link}"

    send_mail(
        subject='Verify Your Email',
        message=email_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )

    return Response({'message': 'Verification email resent.'}, status=status.HTTP_200_OK)
@api_view(['POST'])
def send_password_reset_email(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        domain =settings.FRONTEND_URL  # Replace with your actual domain

        reset_link = f"{domain}/reset-password/{uid}/{token}/"

        send_mail(
            subject="Password Reset Request",
            message=f"Click the link to reset your password: {reset_link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        return Response({'message': 'Password reset link sent successfully.'}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User with this email does not exist.'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
def reset_password(request, uidb64, token):
    password = request.data.get('password')
    if not password:
        return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({'error': 'Invalid link.'}, status=status.HTTP_400_BAD_REQUEST)

    if default_token_generator.check_token(user, token):
        user.set_password(password)
        user.save()
        return Response({'message': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)
    else:
        return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')

    if not all([old_password, new_password, confirm_password]):
        return Response({'error': 'All fields are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({'error': 'New password and confirm password do not match.'}, status=status.HTTP_400_BAD_REQUEST)

    if not user.check_password(old_password):
        return Response({'error': 'Old password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()
    return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
@api_view(['PUT', 'PATCH'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_user(request):
    user = request.user
    data = request.data.copy()

    grade_ids = data.getlist('grades') if hasattr(data, 'getlist') else data.get('grades', [])
    if isinstance(grade_ids, str):
        grade_ids = [grade_ids]

    if grade_ids:
        for grade_id in grade_ids:
            if not Grade.objects.filter(id=grade_id).exists():
                return Response({'error': f'Invalid grade ID: {grade_id}'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = UserUpdateSerializer(user, data=data, partial=True)
    if serializer.is_valid():
        user = serializer.save()

        if grade_ids:
            user.grades.set(grade_ids)

            existing_user_grades = set(
                User_Grade.objects.filter(user=user).values_list('grade_id', flat=True)
            )
            new_grade_ids = set(int(gid) for gid in grade_ids) - existing_user_grades

            for grade_id in new_grade_ids:
                grade = Grade.objects.get(id=grade_id)
                User_Grade.objects.create(user=user, grade=grade)

        return Response({'message': 'User information updated successfully.'}, status=status.HTTP_200_OK)

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
        child_data['username'] = child_data.get('email')
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

            relation, created = ParentChild.objects.get_or_create(parent=parent, child=child_user)

            if not created:
                # Relation already exists
                if relation.status in ['active', 'pending']:
                    return Response({'message': f'Relation already exists with status: {relation.status}'}, status=200)
                else:
                    relation.status = 'pending'
                    relation.save()
                    return Response({'message': 'Child link request sent (pending approval).'}, status=200)

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

    relation_id = request.data.get('relation_id')
    decision = request.data.get('decision')  # 'accept' or 'reject'

    try:
        relation = ParentChild.objects.get(id=relation_id, child=request.user)
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
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def cancel_child_request(request):
    if request.user.role != 'parent':
        return Response({'error': 'Only parents can cancel child requests.'}, status=403)

    relation_id = request.data.get('relation_id')
    if not relation_id:
        return Response({'error': 'Relation ID is required.'}, status=400)

    try:
        relation = ParentChild.objects.get(id=relation_id, parent=request.user)
        relation.status = 'canceled'
        relation.save()
        return Response({'message': 'Child request canceled successfully.'}, status=200)

    except ParentChild.DoesNotExist:
        return Response({'error': 'No such request found.'}, status=404)
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def unlink_child(request):
    if request.user.role != 'parent':
        return Response({'error': 'Only parents can cancel unlink child.'}, status=403)

    relation_id = request.data.get('relation_id')
    if not relation_id:
        return Response({'error': 'Relation ID is required.'}, status=400)

    try:
        relation = ParentChild.objects.get(id=relation_id, parent=request.user)
        relation.status = 'unlinked'
        relation.save()
        return Response({'message': 'Child unlinked successfully.'}, status=200)

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
        'role': user.role,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone_number': user.phone_number,
        'grades': [grade.id for grade in user.grades.all()],

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
            'parent_name':r.parent.first_name + " "+ r.parent.last_name,

            'status': r.status
        }
        for r in pending_requests
    ]
    return Response(result, status=200)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_parent_childs(request):
    if request.user.role != 'parent':
        return Response({'error': 'Only parents can view child requests.'}, status=403)

    pending_requests = request.user.children.filter(status='active')

    result = [
        {
            'relation_id': r.id,
            'child_id': r.child.id,
            'child_email': r.child.username,
            'child_name':r.child.first_name + " " + r.child.last_name,
            'child_grade': r.child.grades.all().values_list('name', flat=True),
            'status': r.status
        }
        for r in pending_requests
    ]
    return Response(result, status=200)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_child_requests(request):
    if request.user.role != 'parent':
        return Response({'error': 'Only parents can view child requests.'}, status=403)

    pending_requests = request.user.children.filter(status='pending')

    result = [
        {
            'relation_id': r.id,
            'child_id': r.child.id,
            'child_email': r.child.username,
            'child_name':r.child.first_name + " " + r.child.last_name,
            'child_grade': r.child.grades.all().values_list('name', flat=True),
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
            'parent_name':r.parent.first_name + " "+ r.parent.last_name,
            'status': r.status
        }
        for r in accepted_requests
    ]
    return Response(result, status=200)




# Adjust to your actual app name

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def track_book_progress(request):
    user = request.user
    book_id = request.data.get('book_id')
    read_pages = request.data.get('read_pages')

    if not book_id or read_pages is None:
        return Response({'error': 'book_id and read_pages are required.'}, status=400)

    try:
        book = Book.objects.get(id=book_id)
    except Book.DoesNotExist:
        return Response({'error': 'Book not found.'}, status=404)

    try:
        read_pages = int(read_pages)
    except ValueError:
        return Response({'error': 'read_pages must be an integer.'}, status=400)

    # Calculate completed_percentage
    if book.total_pages:
        completed_percentage = min((read_pages / book.total_pages) * 100, 100)
    else:
        completed_percentage = 0.0

    # Create or update progress
# Create or update progress
    progress, created = BookProgress.objects.get_or_create(user=user, book=book)

# Only update if this is not a new record AND the new read_pages is greater
    if not created and progress.read_pages >= read_pages:
        return Response({'message': 'Progress not updated because read_pages is less than or equal to existing value.'}, status=200)

    progress.read_pages = read_pages
    progress.completed_percentage = completed_percentage
    progress.save()

    return Response({
        'message': 'Book progress tracked successfully.',
        'book_id': str(book.id),
        'read_pages': read_pages,
        'completed_percentage': round(completed_percentage, 2),
        'last_read_at': progress.last_read_at
    }, status=status.HTTP_200_OK)
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def track_video_progress(request):
    user = request.user
    video_id = request.data.get('video_id')
    watched_seconds = request.data.get('watched_seconds')

    if not video_id or watched_seconds is None:
        return Response({'error': 'video_id and watched_seconds are required.'}, status=400)

    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return Response({'error': 'Video not found.'}, status=404)

    try:
        watched_seconds = int(watched_seconds)
    except ValueError:
        return Response({'error': 'watched_seconds must be an integer.'}, status=400)

    # Calculate completed percentage
    if video.duration and video.duration.total_seconds() > 0:
        completed_percentage = min((watched_seconds / video.duration.total_seconds()) * 100, 100)
    else:
        completed_percentage = 0.0

    # Create or update progress
    progress, created = VideoProgress.objects.get_or_create(user=user, video=video)

    # Only update if this is not a new record AND watched_seconds is greater
    if not created and progress.watched_seconds >= watched_seconds:
        return Response({'message': 'Progress not updated because watched_seconds is less than or equal to existing value.'}, status=200)

    progress.watched_seconds = watched_seconds
    progress.completed_percentage = completed_percentage
    progress.save()

    return Response({
        'message': 'Video progress tracked successfully.',
        'video_id': str(video.id),
        'watched_seconds': watched_seconds,
        'completed_percentage': round(completed_percentage, 2),
        'last_watched_at': progress.last_watched_at
    }, status=status.HTTP_200_OK)

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
        # ✅ Get related subjects, chapters, subsections
        subjects = Subject.objects.filter(grade=grade)
        chapters = Chapter.objects.filter(subject__in=subjects)
        subsections = Subsection.objects.filter(chapter__in=chapters)

        # ✅ Videos
        videos = Video.objects.filter(
            type='class'
        ).filter(
            Q(grade=grade) |
            Q(subject__in=subjects) |
            Q(chapter__in=chapters) |
            Q(subsection__in=subsections)
        )

        # ✅ Books
        books = Book.objects.filter(
            type='class'
        ).filter(
            Q(grade=grade) |
            Q(subject__in=subjects) |
            Q(chapter__in=chapters) |
            Q(subsection__in=subsections)
        )

        # ✅ Exercises (M2M)
        exercises = Exercise.objects.filter(
            type='class'
        ).filter(
            Q(grades=grade) |
            Q(subject__in=subjects) |
            Q(chapter__in=chapters) |
            Q(subsection__in=subsections)
        ).distinct()

        # ✅ IDs
        video_ids = list(videos.values_list('id', flat=True))
        book_ids = list(books.values_list('id', flat=True))
        exercise_ids = list(exercises.values_list('id', flat=True))

        # ✅ Progress records
        video_progress = VideoProgress.objects.filter(user=user, video_id__in=video_ids)
        book_progress = BookProgress.objects.filter(user=user, book_id__in=book_ids)
        exercise_progress = ExerciseProgress.objects.filter(user=user, exercise_id__in=exercise_ids)

        # ✅ Completed percentages
        all_percentages = list(video_progress.values_list('completed_percentage', flat=True)) + \
                          list(book_progress.values_list('completed_percentage', flat=True)) + \
                          list(exercise_progress.values_list('completed_percentage', flat=True))

        total_content = len(video_ids) + len(book_ids) + len(exercise_ids)
        completed_content = len(video_progress) + len(book_progress) + len(exercise_progress)
        average_percentage = round(sum(all_percentages) / total_content, 2) if total_content > 0 else 0.0

        # ✅ Most recent activity
        latest_video = video_progress.order_by('-last_watched_at').first()
        latest_book = book_progress.order_by('-last_read_at').first()
        latest_exercise = exercise_progress.order_by('-last_done_at').first()

        last_dates = [
            getattr(latest_video, 'last_watched_at', None),
            getattr(latest_book, 'last_read_at', None),
            getattr(latest_exercise, 'last_done_at', None)
        ]
        last_watched_at = max([d for d in last_dates if d is not None], default=None)

        result.append({
            'grade_id': grade.id,
            'grade_name': grade.name,
            'total_content': total_content,
            'contents_with_progress': completed_content,
            'average_percentage_completed': average_percentage,
            'last_watched_at': last_watched_at
        })

    # ✅ Sort result by most recent progress
    min_datetime = timezone.make_aware(datetime.min)
    sorted_result = sorted(
        result,
        key=lambda x: x['last_watched_at'] or min_datetime,
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
    user_grades = User_Grade.objects.filter(user=user, is_active=True).select_related('grade')
    grade_ids = [ug.grade.id for ug in user_grades]
    if parent_id not in grade_ids:
        return Response({'class not startted'}, status=200)

    subjects = Subject.objects.filter(grade_id=parent_id)
    result = []

    for subject in subjects:
        # ✅ Directly under subject
        direct_videos = Video.objects.filter(subject=subject, type='class')
        direct_books = Book.objects.filter(subject=subject, type='class')
        direct_exercises = Exercise.objects.filter(subject=subject, type='class')

        # ✅ Under chapters
        chapters = Chapter.objects.filter(subject=subject)
        chapter_videos = Video.objects.filter(chapter__in=chapters, type='class')
        chapter_books = Book.objects.filter(chapter__in=chapters, type='class')
        chapter_exercises = Exercise.objects.filter(chapter__in=chapters, type='class')

        # ✅ Under subsections of chapters
        subsections = Subsection.objects.filter(chapter__in=chapters)
        subsection_videos = Video.objects.filter(subsection__in=subsections, type='class')
        subsection_books = Book.objects.filter(subsection__in=subsections, type='class')
        subsection_exercises = Exercise.objects.filter(subsection__in=subsections, type='class')

        # ✅ Combine all content types
        all_videos = direct_videos | chapter_videos | subsection_videos
        all_books = direct_books | chapter_books | subsection_books
        all_exercises = direct_exercises | chapter_exercises | subsection_exercises

        video_ids = list(all_videos.values_list('id', flat=True))
        book_ids = list(all_books.values_list('id', flat=True))
        exercise_ids = list(all_exercises.values_list('id', flat=True))

        # ✅ Get user progress
        video_progress = VideoProgress.objects.filter(user=user, video_id__in=video_ids)
        book_progress = BookProgress.objects.filter(user=user, book_id__in=book_ids)
        exercise_progress = ExerciseProgress.objects.filter(user=user, exercise_id__in=exercise_ids)

        # ✅ Combine completed percentages
        all_percentages = list(video_progress.values_list('completed_percentage', flat=True)) + \
                          list(book_progress.values_list('completed_percentage', flat=True)) + \
                          list(exercise_progress.values_list('completed_percentage', flat=True))

        total_contents = len(video_ids) + len(book_ids) + len(exercise_ids)
        completed_contents = len(video_progress) + len(book_progress) + len(exercise_progress)
        average_percentage = round(sum(all_percentages) / total_contents, 2) if total_contents else 0.0

        result.append({
            'subject_id': subject.id,
            'subject_name': subject.name,
            'total_content': total_contents,
            'contents_with_progress': completed_contents,
            'average_percentage_completed': average_percentage
        })

    return Response({
        'grade_id': parent_id,
        'level': 'subject',
        'subjects_progress': result
    }, status=200)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def aggregated_progress_subjects_under_user_grades(request):
    user = request.user
    user_grades = User_Grade.objects.filter(user=user, is_active=True).select_related('grade')
    grades = [ug.grade for ug in user_grades]

    result = []

    for grade in grades:
        subjects = Subject.objects.filter(grade=grade)
        for subject in subjects:
            # Collect content
            chapters = Chapter.objects.filter(subject=subject)
            subsections = Subsection.objects.filter(chapter__in=chapters)

            videos = Video.objects.filter(
                Q(subject=subject) | Q(chapter__in=chapters) | Q(subsection__in=subsections),
                type='class'
            )
            books = Book.objects.filter(
                Q(subject=subject) | Q(chapter__in=chapters) | Q(subsection__in=subsections),
                type='class'
            )
            exercises = Exercise.objects.filter(
                Q(subject=subject) | Q(chapter__in=chapters) | Q(subsection__in=subsections),
                type='class'
            )

            video_ids = list(videos.values_list('id', flat=True))
            book_ids = list(books.values_list('id', flat=True))
            exercise_ids = list(exercises.values_list('id', flat=True))

            video_progress = VideoProgress.objects.filter(user=user, video_id__in=video_ids)
            book_progress = BookProgress.objects.filter(user=user, book_id__in=book_ids)
            exercise_progress = ExerciseProgress.objects.filter(user=user, exercise_id__in=exercise_ids)

            all_percentages = list(video_progress.values_list('completed_percentage', flat=True)) + \
                              list(book_progress.values_list('completed_percentage', flat=True)) + \
                              list(exercise_progress.values_list('completed_percentage', flat=True))

            total_contents = len(video_ids) + len(book_ids) + len(exercise_ids)
            completed_contents = len(video_progress) + len(book_progress) + len(exercise_progress)
            average_percentage = round(sum(all_percentages) / total_contents, 2) if total_contents else 0.0

            result.append({
                'grade_id': grade.id,
                'grade_name': grade.name,
                'subject_id': subject.id,
                'subject_name': subject.name,
                'total_content': total_contents,
                'contents_with_progress': completed_contents,
                'average_percentage_completed': average_percentage
            })

    return Response({
        'level': 'subject',
        'subjects_progress': result
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

    chapters = Chapter.objects.filter(subject_id=parent_id)

    if not chapters.exists():
        return Response({'error': 'No chapters found for this subject.'}, status=404)

    # Assuming all chapters under the subject belong to the same grade, we can get the first
    grade_id = chapters.first().subject.grade.id

    user_grades = User_Grade.objects.filter(user=user, is_active=True).select_related('grade')
    grade_ids = [ug.grade.id for ug in user_grades]

    if grade_id not in grade_ids:
        return Response({'error': 'Class not started.'}, status=200)


    result = []

    for chapter in chapters:
        # ✅ Fetch content directly under the chapter (type='class')
        direct_videos = Video.objects.filter(chapter=chapter, type='class')
        direct_books = Book.objects.filter(chapter=chapter, type='class')
        direct_exercises = Exercise.objects.filter(chapter=chapter, type='class')

        # ✅ Fetch content from subsections under this chapter
        subsections = Subsection.objects.filter(chapter=chapter)
        subsection_videos = Video.objects.filter(subsection__in=subsections, type='class')
        subsection_books = Book.objects.filter(subsection__in=subsections, type='class')
        subsection_exercises = Exercise.objects.filter(subsection__in=subsections, type='class')

        # ✅ Combine content
        all_videos = direct_videos | subsection_videos
        all_books = direct_books | subsection_books
        all_exercises = direct_exercises | subsection_exercises

        # ✅ Get IDs
        video_ids = list(all_videos.values_list('id', flat=True))
        book_ids = list(all_books.values_list('id', flat=True))
        exercise_ids = list(all_exercises.values_list('id', flat=True))

        # ✅ Get Progress
        video_progress = VideoProgress.objects.filter(user=user, video_id__in=video_ids)
        book_progress = BookProgress.objects.filter(user=user, book_id__in=book_ids)
        exercise_progress = ExerciseProgress.objects.filter(user=user, exercise_id__in=exercise_ids)

        # ✅ Combine completed_percentage values
        all_percentages = list(video_progress.values_list('completed_percentage', flat=True)) + \
                          list(book_progress.values_list('completed_percentage', flat=True)) + \
                          list(exercise_progress.values_list('completed_percentage', flat=True))

        total_contents = len(video_ids) + len(book_ids) + len(exercise_ids)
        completed_contents = len(video_progress) + len(book_progress) + len(exercise_progress)
        average_percentage = round(sum(all_percentages) / total_contents, 2) if total_contents > 0 else 0.0

        result.append({
            'chapter_id': chapter.id,
            'chapter_title': chapter.title,
            'total_content': total_contents,
            'contents_with_progress': completed_contents,
            'average_percentage_completed': average_percentage
        })

    return Response({
        'subject_id': parent_id,
        'level': 'chapter',
        'chapters_progress': result
    }, status=200)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def aggregated_progress_chapter_level_for_user(request):
    user = request.user
    user_grades = User_Grade.objects.filter(user=user, is_active=True).select_related('grade')
    grades = [ug.grade for ug in user_grades]

    result = []

    for grade in grades:
        subjects = grade.subjects.all()  # Assuming reverse relation exists
        for subject in subjects:
            chapters = Chapter.objects.filter(subject=subject)
            for chapter in chapters:
                subsections = Subsection.objects.filter(chapter=chapter)

                videos = Video.objects.filter(
                    Q(chapter=chapter) | Q(subsection__in=subsections),
                    type='class'
                )
                books = Book.objects.filter(
                    Q(chapter=chapter) | Q(subsection__in=subsections),
                    type='class'
                )
                exercises = Exercise.objects.filter(
                    Q(chapter=chapter) | Q(subsection__in=subsections),
                    type='class'
                )

                video_ids = list(videos.values_list('id', flat=True))
                book_ids = list(books.values_list('id', flat=True))
                exercise_ids = list(exercises.values_list('id', flat=True))

                video_progress = VideoProgress.objects.filter(user=user, video_id__in=video_ids)
                book_progress = BookProgress.objects.filter(user=user, book_id__in=book_ids)
                exercise_progress = ExerciseProgress.objects.filter(user=user, exercise_id__in=exercise_ids)

                all_percentages = list(video_progress.values_list('completed_percentage', flat=True)) + \
                                  list(book_progress.values_list('completed_percentage', flat=True)) + \
                                  list(exercise_progress.values_list('completed_percentage', flat=True))

                total_contents = len(video_ids) + len(book_ids) + len(exercise_ids)
                completed_contents = len(video_progress) + len(book_progress) + len(exercise_progress)
                average_percentage = round(sum(all_percentages) / total_contents, 2) if total_contents > 0 else 0.0

                result.append({
                    'grade_id': grade.id,
                    'grade_name': grade.name,
                    'subject_id': subject.id,
                    'subject_name': subject.name,
                    'chapter_id': chapter.id,
                    'chapter_title': chapter.title,
                    'total_content': total_contents,
                    'contents_with_progress': completed_contents,
                    'average_percentage_completed': average_percentage
                })

    return Response({
        'level': 'chapter',
        'chapters_progress': result
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
        videos = Video.objects.filter(subsection=subsection, type='class')
        books = Book.objects.filter(subsection=subsection, type='class')
        exercises = Exercise.objects.filter(subsection=subsection, type='class')
        # Get IDs
        video_ids = list(videos.values_list('id', flat=True))
        book_ids = list(books.values_list('id', flat=True))
        exercise_ids = list(exercises.values_list('id', flat=True))

        # Progress data
        video_progress = VideoProgress.objects.filter(user=user, video_id__in=video_ids)
        book_progress = BookProgress.objects.filter(user=user, book_id__in=book_ids)
        exercise_progress = ExerciseProgress.objects.filter(user=user, exercise_id__in=exercise_ids)

        # Combine all percentages
        all_percentages = list(video_progress.values_list('completed_percentage', flat=True)) + \
                          list(book_progress.values_list('completed_percentage', flat=True)) + \
                          list(exercise_progress.values_list('completed_percentage', flat=True))

        total_content_count = len(video_ids) + len(book_ids) + len(exercise_ids)
        completed_content_count = len(video_progress) + len(book_progress) + len(exercise_progress)
        average_percentage = round(sum(all_percentages) / total_content_count, 2) if total_content_count else 0.0

        result.append({
            'subsection_id': subsection.id,
            'subsection_title': subsection.title,
            'total_content': total_content_count,
            'contents_with_progress': completed_content_count,
            'average_percentage_completed': average_percentage
        })

    return Response({
        'chapter_id': parent_id,
        'level': 'subsection',
        'subsections_progress': result
    }, status=200)






@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_progress(request, content_type, content_id):
    user = request.user

    def get_grade_from_content(content):
        if hasattr(content, 'subsection') and content.subsection and content.subsection.chapter and content.subsection.chapter.subject:
            return content.subsection.chapter.subject.grade
        elif hasattr(content, 'chapter') and content.chapter and content.chapter.subject:
            return content.chapter.subject.grade
        elif hasattr(content, 'subject') and content.subject:
            return content.subject.grade
        elif hasattr(content, 'grade') and content.grade:
            return content.grade
        return None

    if content_type == 'video':
        try:
            video = Video.objects.get(pk=content_id)
            progress, created = VideoProgress.objects.get_or_create(user=user, video=video, defaults={
                'completed_percentage': 0.0,
                'watched_seconds': 0
            })
            if created:
                grade = get_grade_from_content(video)
                if grade:
                    user_grade, ug_created = User_Grade.objects.get_or_create(user=user, grade=grade)
                    if ug_created or not user_grade.is_active:
                        user_grade.is_active = True
                        user_grade.save()
            return Response({
                'type': 'video',
                'completed_percentage': float(progress.completed_percentage),
                'watched_seconds': progress.watched_seconds,
                'duration_seconds': video.duration.total_seconds() if video.duration else None,
                'last_watched_at': progress.last_watched_at
            })
        except Video.DoesNotExist:
            return Response({'error': 'Video not found.'}, status=404)

    elif content_type == 'book':
        try:
            book = Book.objects.get(pk=content_id)
            progress, created = BookProgress.objects.get_or_create(user=user, book=book, defaults={
                'completed_percentage': 0.0,
                'read_pages': 0
            })
            if created:
                grade = get_grade_from_content(book)
                if grade:
                    user_grade, ug_created = User_Grade.objects.get_or_create(user=user, grade=grade)
                    if ug_created or not user_grade.is_active:
                        user_grade.is_active = True
                        user_grade.save()
            return Response({
                'type': 'book',
                'completed_percentage': float(progress.completed_percentage),
                'read_pages': progress.read_pages,
                'total_pages': book.total_pages,
                'last_read_at': progress.last_read_at
            })
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=404)

    elif content_type == 'exercise':
        try:
            exercise = Exercise.objects.get(pk=content_id)
            progress, created = ExerciseProgress.objects.get_or_create(user=user, exercise=exercise, defaults={
                'completed_percentage': 0.0,
                'done_exercises': 0
            })
            if created:
                grade = get_grade_from_content(exercise)
                if grade:
                    user_grade, ug_created = User_Grade.objects.get_or_create(user=user, grade=grade)
                    if ug_created or not user_grade.is_active:
                        user_grade.is_active = True
                        user_grade.save()
            return Response({
                'type': 'exercise',
                'completed_percentage': float(progress.completed_percentage),
                'done_exercises': progress.done_exercises,
                'total_exercises': exercise.total_exercise,
                'last_done_at': progress.last_done_at
            })
        except Exercise.DoesNotExist:
            return Response({'error': 'Exercise not found.'}, status=404)

    return Response({'error': 'Invalid content type. Use "video", "book", or "exercise".'}, status=400)






    
