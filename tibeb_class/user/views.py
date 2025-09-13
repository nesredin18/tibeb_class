from decimal import Decimal
from functools import cache
import uuid
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from tibeb_class.sms_templates import SMSTemplateHelper
from tibeb_class.permissions import IsVerified
from user.utils import send_sms_otp
from .serializers import UserSerializer, UserUpdateSerializer
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from .models import BookProgress, CustomUser, ExerciseAnswer, ExerciseProgress, ParentChild, PasswordResetOTP, PhoneOTP, QuestionProgress, User_Grade,UserSubscription, VideoProgress,BookProgress
from contents.models import Book, Exercise, Option, Question, Subject, Subsection
from subscription.models import SubscriptionPlan
from contents.models import Grade,Video, Chapter
from datetime import datetime
from django.db.models import Q
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings
from fuzzywuzzy import fuzz
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from tibeb_class.email_templates import EmailTemplateHelper
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
import re
from django.core.validators import validate_email
from django.core.exceptions import ValidationError






User = get_user_model()

# Create your views here.
@api_view(['POST'])
def login(request):
    username = request.data.get('username')  # you're using 'email' as username
    password = request.data.get('password')
    remember_me = request.data.get('remember_me', False)

    user = authenticate(username=username, password=password)

    if user is None:
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)
    if not user.is_verified:
        return Response({'error': 'Account not verified. Please verify your account.'}, status=status.HTTP_403_FORBIDDEN)

    # Create a refresh token
    refresh = RefreshToken.for_user(user)

    # Adjust expiration based on remember_me flag
    if remember_me:
        refresh.set_exp(lifetime=timedelta(days=7))
        refresh.access_token.set_exp(lifetime=timedelta(days=1))
    else:
        refresh.set_exp(lifetime=timedelta(hours=24))
        refresh.access_token.set_exp(lifetime=timedelta(minutes=180))

    user_serializer = UserSerializer(user)

    return Response({
        'token': str(refresh.access_token),
        'refresh': str(refresh),
        'user': user_serializer.data
    }, status=status.HTTP_200_OK)
def is_strong_password(password):
    return (
        len(password) >= 8 and
        re.search(r'[A-Z]', password) and
        re.search(r'[a-z]', password) and
        re.search(r'\d', password) and
        re.search(r'[!@#$%^&*(),.?":{}|<>]', password)
    )
@api_view(['POST'])
def signup(request):
    data = request.data.copy()
    email = data.get('email')
    phone = data.get('phone_number')

    if not email and not phone:
        return Response({'error': 'Either email or phone number is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if email and phone:
        return Response(
            {'error': 'Provide only one: email or phone number, not both.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if phone:
        phone_pattern = re.compile(r"^09\d{8}$")
        if not phone_pattern.match(phone):
            return Response(
                {'error': 'Invalid phone number. Must be 10 digits and start with 09 (e.g. 0932808120).'},
                status=status.HTTP_400_BAD_REQUEST
            )

    if email:
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {'error': 'Invalid email address.'},
                status=status.HTTP_400_BAD_REQUEST
            )
    if email:
        data['username'] = email
        data['username_type'] = 'email'
    elif phone:  
        data['username'] = phone 
        data['username_type'] = 'phone'
    if not is_strong_password(data.get('password')):
        return Response({'password': [
            "Password must be at least 8 characters, include uppercase, lowercase, number, and special character."
        ]}, status=status.HTTP_400_BAD_REQUEST)
    # Handle grades input (supports list or single value)
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

        # Assign grades
        grades = user.grades.all()
        for grade in grades:
            User_Grade.objects.create(user=user, grade=grade)


        return Response({'message': 'User Created Succesfully'}, status=status.HTTP_200_OK)

    # Handle username -> email error
    errors = dict(serializer.errors)

    return Response(errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def verify_username(request):
    username = request.data.get('username')
    code = request.data.get('code')
    if not username or not code:
        return Response({'error': 'Username and code are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        otp_obj = PhoneOTP.objects.get(user__username=username, otp=code, is_used=False)
    except PhoneOTP.DoesNotExist:
        return Response({'error': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)

    # Mark OTP as used
    otp_obj.is_used = True
    otp_obj.save()

    # Verify user
    user = otp_obj.user
    user.is_verified = True
    user.save()

    return Response({
        'message': 'username verified successfully.',
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
def resend_verification_code(request):
    username = request.data.get('username')
    user = CustomUser.objects.get(username=username)
    if not user:
        return Response({'error': 'User not found.'}, status=404)
    if user.is_verified:  # Assuming you have a boolean field `is_verified` on your CustomUser model
        return Response({'message': 'User is already verified.'}, status=status.HTTP_400_BAD_REQUEST)

    if user.username_type == 'email':
        otp_obj = PhoneOTP.objects.create(user=user)
        html = EmailTemplateHelper.verify_email_html(otp_obj.otp)
        text = strip_tags(html)
        msg = EmailMultiAlternatives(
            subject="Verify Your Email",
            body=text,  # plain-text
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.username], 
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    elif user.username_type == 'phone':
        otp_obj = PhoneOTP.objects.create(user=user)
        send_sms_otp(user.username, otp_obj.otp)

    return Response({'message': 'Verification code resent.'}, status=status.HTTP_200_OK)
@api_view(['POST'])
def send_password_reset_code(request):
    username = request.data.get('username')
    try:
        user = CustomUser.objects.get(username=username)
    except CustomUser.DoesNotExist:
        user = None

    if not user:
        return Response({'error': 'User not found.'}, status=404)
    if user.username_type == 'email':
        otp_obj = PasswordResetOTP.objects.create(user=user)
        html = EmailTemplateHelper.forgot_password_html(otp_obj.otp)
        text = strip_tags(html)
        msg = EmailMultiAlternatives(
            subject="Password Reset Request",
            body=text,  # plain-text
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.username], 
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    elif user.username_type == 'phone':
        otp_obj = PasswordResetOTP.objects.create(user=user)
        msg = SMSTemplateHelper.password_reset_otp(otp_obj.otp)
        send_sms_otp(user.username, msg)

    return Response({'message': 'Password reset code sent successfully.'}, status=status.HTTP_200_OK)
@api_view(['POST'])
def verify_password_reset_code(request):
    username = request.data.get("username")
    code = request.data.get("code")
    if not username or not code:
        return Response({"error": "Username and code are required."}, status=400)

    try:
        user = CustomUser.objects.get(username=username) 
        otp_obj = PasswordResetOTP.objects.filter(user=user, otp=code, is_used=False).last()
    except CustomUser.DoesNotExist:
        return Response({"error": "Invalid user"}, status=400)

    if not otp_obj or otp_obj.is_expired():
        return Response({"error": "Code expired or invalid"}, status=400)

    # Mark OTP as used
    otp_obj.is_used = True
    otp_obj.save()

    # ✅ Generate Django password reset token instead of uuid
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    return Response({
        "message": "Code verified",
        "uid": uid,
        "token": token
    }, status=200)

@api_view(['POST'])
def reset_password(request, uidb64, token):
    password = request.data.get('password')
    if not password:
        return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not is_strong_password(password):
        return Response({'password': [
            "Password must be at least 8 characters, include uppercase, lowercase, number, and special character."
        ]}, status=status.HTTP_400_BAD_REQUEST)

    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({'error': 'Invalid code.'}, status=status.HTTP_400_BAD_REQUEST)

    if default_token_generator.check_token(user, token):
        user.set_password(password)
        if not user.is_verified:
            user.is_verified = True
        user.save()
        return Response({'message': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)
    else:
        return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
def change_password(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')

    if not all([old_password, new_password, confirm_password]):
        return Response({'error': 'All fields are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({'error': 'New password and confirm password do not match.'}, status=status.HTTP_400_BAD_REQUEST)
    if not is_strong_password(new_password):
        return Response({'password': [
            "Password must be at least 8 characters, include uppercase, lowercase, number, and special character."
        ]}, status=status.HTTP_400_BAD_REQUEST)
    if not user.check_password(old_password):
        return Response({'error': 'Old password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()
    return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
def update_email_and_send_verification(request):
    new_email = request.data.get('email')

    if not new_email:
        return Response({'error': 'Email is required.'}, status=400)

    user = request.user
    if user.last_email_change and timezone.now() - user.last_email_change < timedelta(days=30):
        return Response(
            {'error': 'You can only change your email once every 30 days.'},
            status=400
        )
    user.email = new_email
    user.username=new_email
    user.is_verified = False
    user.last_email_change = timezone.now()   # record timestamp


    try:
        user.save()
    except IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            return Response({'error': 'Email already taken.'}, status=400)
        return Response({'error': 'An unexpected error occurred.'}, status=500)

    # Send new verification email
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    domain = settings.FRONTEND_URL

    verification_link = f"{domain}/verify-email/{uid}/{token}/"

    send_mail(
        subject='Verify Your New Email Address',
        message=f'Click the link to verify your email: {verification_link}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[new_email],
    )

    return Response({'message': 'Email updated and verification sent.'}, status=200)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
def test(request):
        
        return Response("passed for {}".format(request.user.username), status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
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

        child_data['role'] = 'student'
        child_data['username'] = child_data.get('email')
        
        grade_ids = child_data.getlist('grades') if hasattr(child_data, 'getlist') else child_data.get('grades', [])
        if isinstance(grade_ids, str):
            grade_ids = [grade_ids]

        # Validate grade IDs if provided
        for grade_id in grade_ids:
            if not Grade.objects.filter(id=grade_id).exists():
                return Response({'error': f'Invalid grade ID: {grade_id}'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = UserSerializer(data=child_data)
        if serializer.is_valid():
            child_user = serializer.save()

            # Create parent-child relation
            ParentChild.objects.create(parent=parent, child=child_user, status='active')

            # Assign grades if any
            for grade_id in grade_ids:
                grade = Grade.objects.get(id=grade_id)
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
                    return Response({'error': f'Relation already exists with status: {relation.status}'}, status=400)
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
@permission_classes([IsAuthenticated, IsVerified])
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
    progress.save()

    return Response({
        'message': 'Book progress tracked successfully.',
        'book_id': str(book.id),
        'read_pages': read_pages,
        'completed_percentage': round(completed_percentage, 2),
        'last_read_at': progress.last_read_at
    }, status=status.HTTP_200_OK)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
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
    progress.save()

    return Response({
        'message': 'Video progress tracked successfully.',
        'video_id': str(video.id),
        'watched_seconds': watched_seconds,
        'completed_percentage': round(completed_percentage, 2),
        'last_watched_at': progress.last_watched_at
    }, status=status.HTTP_200_OK)



@api_view(['POST'])

@permission_classes([IsAuthenticated, IsVerified])
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

@permission_classes([IsAuthenticated, IsVerified])
def get_active_subscription(request):
    user = request.user
    today = timezone.now().date()
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
        except CustomUser.DoesNotExist:
            return Response({'error': 'Child user not found.'}, status=404)

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

@permission_classes([IsAuthenticated, IsVerified])
def user_grade(request):
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
        except CustomUser.DoesNotExist:
            return Response({'error': 'Child user not found.'}, status=404)
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

@permission_classes([IsAuthenticated, IsVerified])
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

@permission_classes([IsAuthenticated, IsVerified])
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
        video_percentages = [
            min(Decimal(p.watched_seconds) / Decimal(p.video.duration.total_seconds()), 1.0) * 100
            for p in video_progress
            if p.video and p.video.duration.total_seconds() > 0
        ]

        book_percentages = [
            min(Decimal(p.read_pages) / Decimal(p.book.total_pages), 1.0) * 100
            for p in book_progress
            if p.book and p.book.total_pages > 0
        ]

        exercise_percentages = [
            min(Decimal(p.done_exercises) / Decimal(p.exercise.total_exercise), 1.0) * 100
            for p in exercise_progress
            if p.exercise and p.exercise.total_exercise > 0
        ]

        # Combine all percentages
        all_percentages = video_percentages + book_percentages + exercise_percentages

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

@permission_classes([IsAuthenticated, IsVerified])
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
# ✅ Calculate completed percentages
        video_percentages = [
            min(Decimal(p.watched_seconds) / Decimal(p.video.duration.total_seconds()), 1.0) * 100
            for p in video_progress
            if p.video and p.video.duration.total_seconds() > 0
        ]
        book_percentages = [
            min(Decimal(p.read_pages) / Decimal(p.book.total_pages), 1.0) * 100
            for p in book_progress
            if p.book and p.book.total_pages > 0
        ]

        exercise_percentages = [
            min(Decimal(p.done_exercises) / Decimal(p.exercise.total_exercise), 1.0) * 100
            for p in exercise_progress
            if p.exercise and p.exercise.total_exercise > 0
        ]

        # Combine all percentages
        all_percentages = video_percentages + book_percentages + exercise_percentages

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

@permission_classes([IsAuthenticated, IsVerified])
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

    # ✅ Calculate completed percentages
            video_percentages = [
                min(Decimal(p.watched_seconds) / Decimal(p.video.duration.total_seconds()), 1.0) * 100
                for p in video_progress
                if p.video and p.video.duration.total_seconds() > 0
            ]

            book_percentages = [
                min(Decimal(p.read_pages) / Decimal(p.book.total_pages), 1.0) * 100
                for p in book_progress
                if p.book and p.book.total_pages > 0
            ]

            exercise_percentages = [
                min(Decimal(p.done_exercises) / Decimal(p.exercise.total_exercise), 1.0) * 100
                for p in exercise_progress
                if p.exercise and p.exercise.total_exercise > 0
            ]

            # Combine all percentages
            all_percentages = video_percentages + book_percentages + exercise_percentages

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

@permission_classes([IsAuthenticated, IsVerified])
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

# ✅ Calculate completed percentages
        video_percentages = [
            min(Decimal(p.watched_seconds) / Decimal(p.video.duration.total_seconds()), 1.0) * 100
            for p in video_progress
            if p.video and p.video.duration.total_seconds() > 0
        ]

        book_percentages = [
            min(Decimal(p.read_pages) / Decimal(p.book.total_pages), 1.0) * 100
            for p in book_progress
            if p.book and p.book.total_pages > 0
        ]

        exercise_percentages = [
            min(Decimal(p.done_exercises) / Decimal(p.exercise.total_exercise), 1.0) * 100
            for p in exercise_progress
            if p.exercise and p.exercise.total_exercise > 0
        ]

        # Combine all percentages
        all_percentages = video_percentages + book_percentages + exercise_percentages

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

@permission_classes([IsAuthenticated, IsVerified])
def aggregated_progress_chapter_level_for_user(request):
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
        except CustomUser.DoesNotExist:
            return Response({'error': 'Child user not found.'}, status=404)
        
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

        # ✅ Calculate completed percentages
                video_percentages = [
                    min(Decimal(p.watched_seconds) / Decimal(p.video.duration.total_seconds()), 1.0) * 100
                    for p in video_progress
                    if p.video and p.video.duration.total_seconds() > 0
                ]

                book_percentages = [
                    min(Decimal(p.read_pages) / Decimal(p.book.total_pages), 1.0) * 100
                    for p in book_progress
                    if p.book and p.book.total_pages > 0
                ]

                exercise_percentages = [
                    min(Decimal(p.done_exercises) / Decimal(p.exercise.total_exercise), 1.0) * 100
                    for p in exercise_progress
                    if p.exercise and p.exercise.total_exercise > 0
                ]

                # Combine all percentages
                all_percentages = video_percentages + book_percentages + exercise_percentages

                total_contents = len(video_ids) + len(book_ids) + len(exercise_ids)
                completed_contents = len(video_progress) + len(book_progress) + len(exercise_progress)
                average_percentage = round(sum(all_percentages) / total_contents, 2) if total_contents > 0 else 0.0
                # ✅ NEW: Question correctness calculation
                question_progress_qs = QuestionProgress.objects.filter(user=user, exercise_id__in=exercise_ids)
                total_questions_answered = question_progress_qs.count()

                correct_count = 0
                from fuzzywuzzy import fuzz

                for qp in question_progress_qs:
                    if qp.question.question_type == 'choose':
                        if qp.selected_option and qp.selected_option.is_correct:
                            correct_count += 1
                    elif qp.question.question_type == 'write':
                        correct_answer = qp.question.answer.strip().lower()
                        user_answer = qp.answer_text.strip().lower()
                        similarity = fuzz.ratio(correct_answer, user_answer)
                        if similarity >= 80:
                            correct_count += 1

                correct_percentage = (
    round((correct_count / total_questions_answered) * 100, 2)
    if total_questions_answered > 0 else None  # or "N/A"
)


                result.append({
                    'grade_id': grade.id,
                    'grade_name': grade.name,
                    'subject_id': subject.id,
                    'subject_name': subject.name,
                    'chapter_id': chapter.id,
                    'chapter_title': chapter.title,
                    'total_content': total_contents,
                    'contents_with_progress': completed_contents,
                    'average_percentage_completed': average_percentage,
                    'exercise_correct_answer_percentage': correct_percentage  # ✅ NEW FIELD

                })

    return Response({
        'level': 'chapter',
        'chapters_progress': result
    }, status=200)


@api_view(['GET'])

@permission_classes([IsAuthenticated, IsVerified])
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
# ✅ Calculate completed percentages
        video_percentages = [
            min(Decimal(p.watched_seconds) / Decimal(p.video.duration.total_seconds()), 1.0) * 100
            for p in video_progress
            if p.video and p.video.duration.total_seconds() > 0
        ]

        book_percentages = [
            min(Decimal(p.read_pages) / Decimal(p.book.total_pages), 1.0) * 100
            for p in book_progress
            if p.book and p.book.total_pages > 0
        ]

        exercise_percentages = [
            min(Decimal(p.done_exercises) / Decimal(p.exercise.total_exercise), 1.0) * 100
            for p in exercise_progress
            if p.exercise and p.exercise.total_exercise > 0
        ]

        # Combine all percentages
        all_percentages = video_percentages + book_percentages + exercise_percentages

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

@permission_classes([IsAuthenticated, IsVerified])
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
            progress, _ = VideoProgress.objects.get_or_create(user=user, video=video, defaults={'watched_seconds': 0})

            # Add user-grade if new
            if _:
                grade = get_grade_from_content(video)
                if grade:
                    user_grade, created = User_Grade.objects.get_or_create(user=user, grade=grade)
                    if created or not user_grade.is_active:
                        user_grade.is_active = True
                        user_grade.save()

            duration = video.duration.total_seconds() if video.duration else 0
            completed_percentage = (progress.watched_seconds / duration)*100 if duration > 0 else 0.0

            return Response({
                'type': 'video',
                'completed_percentage': round(min(completed_percentage, 100.0), 2),
                'watched_seconds': progress.watched_seconds,
                'duration_seconds': duration,
                'last_watched_at': progress.last_watched_at
            })

        except Video.DoesNotExist:
            return Response({'error': 'Video not found.'}, status=404)

    elif content_type == 'book':
        try:
            book = Book.objects.get(pk=content_id)
            progress, _ = BookProgress.objects.get_or_create(user=user, book=book, defaults={'read_pages': 0})

            if _:
                grade = get_grade_from_content(book)
                if grade:
                    user_grade, created = User_Grade.objects.get_or_create(user=user, grade=grade)
                    if created or not user_grade.is_active:
                        user_grade.is_active = True
                        user_grade.save()

            total_pages = book.total_pages or 0
            completed_percentage = (progress.read_pages / total_pages)*100 if total_pages > 0 else 0.0

            return Response({
                'type': 'book',
                'completed_percentage': round(min(completed_percentage, 100.0), 2),
                'read_pages': progress.read_pages,
                'total_pages': total_pages,
                'last_read_at': progress.last_read_at
            })

        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=404)

    elif content_type == 'exercise':
        try:
            exercise = Exercise.objects.get(pk=content_id)
            progress, _ = ExerciseProgress.objects.get_or_create(user=user, exercise=exercise, defaults={'done_exercises': 0})

            if _:
                grade = get_grade_from_content(exercise)
                if grade:
                    user_grade, created = User_Grade.objects.get_or_create(user=user, grade=grade)
                    if created or not user_grade.is_active:
                        user_grade.is_active = True
                        user_grade.save()

            total = exercise.total_exercise or 0
            completed_percentage = (progress.done_exercises / total)*100 if total > 0 else 0.0

            return Response({
                'type': 'exercise',
                'completed_percentage': round(min(completed_percentage, 100.0), 2),
                'done_exercises': progress.done_exercises,
                'total_exercises': total,
                'last_done_at': progress.last_done_at
            })

        except Exercise.DoesNotExist:
            return Response({'error': 'Exercise not found.'}, status=404)

    return Response({'error': 'Invalid content type. Use "video", "book", or "exercise".'}, status=400)

@api_view(['POST'])

@permission_classes([IsAuthenticated, IsVerified])
def submit_exercise_answer(request):
    user = request.user
    question_id = request.data.get('question_id')
    selected_option_id = request.data.get('selected_option_id')
    written_answer = request.data.get('written_answer', '').strip()

    try:
        question = Question.objects.get(id=question_id)
    except Question.DoesNotExist:
        return Response({'error': 'Question not found'}, status=404)

    # Check if already answered
    answer_obj, created = ExerciseAnswer.objects.get_or_create(
        user=user,
        question=question,
        defaults={
            'exercise': question.exercises.first(),  # assumes 1 exercise per question
            'answered_at': timezone.now()
        }
    )

    # Handle 'choose'
    if question.question_type == 'choose':
        try:
            selected_option = Option.objects.get(id=selected_option_id, question=question)
            answer_obj.selected_option = selected_option
            answer_obj.is_correct = selected_option.is_correct
        except Option.DoesNotExist:
            return Response({'error': 'Invalid option'}, status=400)

    # Handle 'write'
    elif question.question_type == 'write':
        answer_obj.written_answer = written_answer
        # Simple match (optional: use fuzzy matching)
        answer_obj.is_correct = question.answer.strip().lower() == written_answer.lower()
        similarity = fuzz.ratio(written_answer.strip().lower(), question.answer.strip().lower())
        is_correct = similarity >= 80

    answer_obj.save()

    # ✅ Update ExerciseProgress
    exercise = answer_obj.exercise
    progress, _ = ExerciseProgress.objects.get_or_create(user=user, exercise=exercise)
    total_answered = ExerciseAnswer.objects.filter(user=user, exercise=exercise).count()
    progress.done_exercises = total_answered
    progress.save(update_fields=["done_exercises", "last_done_at"])

    return Response({
        'status': 'Answer saved',
        'is_correct': answer_obj.is_correct
    })
@api_view(['POST'])

@permission_classes([IsAuthenticated, IsVerified])
def reset_question_progress_for_exercise(request):
    user = request.user
    exercise_id = request.data.get('exercise_id')

    if not exercise_id:
        return Response({'error': 'exercise_id is required.'}, status=400)

    try:
        exercise = Exercise.objects.get(id=exercise_id)
    except Exercise.DoesNotExist:
        return Response({'error': 'Exercise not found.'}, status=404)

    deleted_count, _ = QuestionProgress.objects.filter(user=user, exercise=exercise).delete()

    return Response({
        'status': 'success',
        'message': f'{deleted_count} progress entries reset for exercise {exercise.id}.'
    }, status=200)





    
