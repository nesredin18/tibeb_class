import os
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from subscription.models import Payment
from configuration.models import Configuration
from tibeb_class.permissions import IsVerified
from user.models import ExerciseProgress, QuestionProgress
from .models import Announcement, Grade, Subject, Book, Chapter, Subsection, Exercise, Video
from .serializers import AnnouncementSerializer, GradeSerializer, QuestionSerializer, SubjectSerializer, BookSerializer, ChapterSerializer, SubsectionSerializer, ExerciseSerializer, VideoSerializer
import random
from fuzzywuzzy import fuzz
from .models import Question, Option
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone



@api_view(['GET'])
def get_grades(request):
    grades = Grade.objects.all().order_by('rank')
    serializer = GradeSerializer(grades, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def get_announcements(request):
    platform = (request.query_params.get('platform') or '').strip().lower()
    announcements = Announcement.objects.filter(is_active=True)
    if platform in {'web', 'mobile'}:
        announcements = announcements.filter(Q(platform='both') | Q(platform=platform))
    serializer = AnnouncementSerializer(
        announcements,
        many=True,
        context={'request': request},
    )
    return Response(serializer.data)

@api_view(['GET'])
def get_subjects(request):
    subjects = Subject.objects.all().order_by('rank')
    serializer = SubjectSerializer(subjects, many=True)
    return Response(serializer.data)
@api_view(['GET'])
def subjects_by_grade(request, grade_id):
    try:
        grade = Grade.objects.get(id=grade_id)
    except Grade.DoesNotExist:
        return Response({'error': 'Grade not found'}, status=status.HTTP_404_NOT_FOUND)

    subjects = Subject.objects.filter(grade=grade).order_by('rank')
    serializer = SubjectSerializer(subjects, many=True)

    return Response({
        'grade_id': grade.id,
        'grade_name': grade.name,
        'subjects': serializer.data
    }, status=200)

@api_view(['GET'])
def get_books(request):
    books = Book.objects.all().order_by('rank')
    serializer = BookSerializer(books, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_chapters(request):
    chapters = Chapter.objects.all().order_by('rank')
    serializer = ChapterSerializer(chapters, many=True)
    return Response(serializer.data)
@api_view(['GET'])
def get_chapter_by_id(request, chapter_id):
    try:
        chapter = Chapter.objects.get(id=chapter_id)
    except Chapter.DoesNotExist:
        return Response({'error': 'Chapter not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = ChapterSerializer(chapter)

    return Response(serializer.data, status=200)
@api_view(['GET'])
def chapters_by_subject(request, subject_id):
    try:
        subject = Subject.objects.get(id=subject_id)
    except Subject.DoesNotExist:
        return Response({'error': 'Subject not found'}, status=status.HTTP_404_NOT_FOUND)

    chapters = Chapter.objects.filter(subject=subject).order_by('rank')
    serializer = ChapterSerializer(chapters, many=True)

    return Response({
        'grade_id': subject.grade.id,
        'grade_name': subject.grade.name,
        'subject_id': subject.id,
        'subject_name': subject.name,
        'chapters': serializer.data
    }, status=200)

@api_view(['GET'])
def get_subsections(request):
    subsections = Subsection.objects.all().order_by('rank')
    serializer = SubsectionSerializer(subsections, many=True)
    return Response(serializer.data)
@api_view(['GET'])
def get_subsection_by_id(request, subsection_id):
    try:
        subsection = Subsection.objects.get(id=subsection_id)
    except Subsection.DoesNotExist:
        return Response({'error': 'Subsection not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = SubsectionSerializer(subsection)
    return Response(serializer.data, status=200)

@api_view(['GET'])
def subsections_by_chapter(request, chapter_id):
    try:
        chapter = Chapter.objects.get(id=chapter_id)
    except Chapter.DoesNotExist:
        return Response({'error': 'Chapter not found'}, status=status.HTTP_404_NOT_FOUND)

    subsections = Subsection.objects.filter(chapter=chapter).order_by('rank')
    serializer = SubsectionSerializer(subsections, many=True)

    return Response({
        'grade_id': chapter.subject.grade.id,
        'grade_name': chapter.subject.grade.name,
        'subject_id': chapter.subject.id,
        'subject_name': chapter.subject.name,
        'chapter_id': chapter.id,
        'chapter_name': chapter.title,
        'subsections': serializer.data
    }, status=200)

@api_view(['GET'])
def get_exercises(request):
    exercises = Exercise.objects.all().order_by('rank')
    serializer = ExerciseSerializer(exercises, many=True)
    return Response(serializer.data)
@api_view(['GET'])
def get_exercises_by_id(request, exercises_id):
    try:
        exercises = Exercise.objects.get(id=exercises_id)
    except Exercise.DoesNotExist:
        return Response({'error': 'Exercise not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ExerciseSerializer(exercises)
    return Response(serializer.data, status=200)

@api_view(['GET'])
def get_exercise_question(request, exercise_id):
    index = int(request.query_params.get('index', 0))  # Get the question index from query param

    try:
        exercise = Exercise.objects.get(id=exercise_id, is_active=True)
    except Exercise.DoesNotExist:
        return Response({"error": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)

    # Get ordered questions
    questions = exercise.questions.all().order_by('rank')

    if questions.count() == 0:
        return Response({"error": "No questions found for this exercise"}, status=status.HTTP_404_NOT_FOUND)

    if index < 0 or index >= questions.count():
        return Response({"error": "Invalid question index"}, status=status.HTTP_400_BAD_REQUEST)

    question = questions[index]
    serializer = QuestionSerializer(question)

    return Response({
        "question_index": index,
        "question_total": questions.count(),
        "question_data": serializer.data
    })

@api_view(['GET'])
def get_videos(request):
    videos = Video.objects.all().order_by('rank')
    serializer = VideoSerializer(videos, many=True)
    return Response(serializer.data)

def user_has_valid_subscription_for_grade(user, grade):
    """
    Helper function to check if the user has a valid, non-expired, paid subscription for the given grade.
    """
    return Payment.objects.filter(
        user=user,
        status='active',
        payment_status='completed',  # Payment must be completed
        grade=grade,
        end_date__gt=timezone.now()  # Ensure the subscription is not expired
    ).exists()

@api_view(['GET'])
def get_content_by_type_and_level(request):
    content_type = request.query_params.get('type')        # 'video', 'book', 'exercise'
    level = request.query_params.get('level')              # 'grade', 'subject', etc.
    parent_id = request.query_params.get('id')
    config = Configuration.objects.first()

    if not content_type or not level or not parent_id:
        return Response({'error': 'Parameters "type", "level", and "id" are required.'}, status=400)

    try:
        parent_id = int(parent_id)
    except ValueError:
        return Response({'error': '"id" must be an integer.'}, status=400)

    if content_type == 'video':
        model = Video
        serializer_class = VideoSerializer
    elif content_type == 'book':
        model = Book
        serializer_class = BookSerializer
    elif content_type == 'exercise':
        model = Exercise
        serializer_class = ExerciseSerializer
    else:
        return Response({'error': 'Invalid type. Must be one of: video, book, exercise.'}, status=400)

    # Direct filter based on the level
    if level == 'grade':
        contents = model.objects.filter(type='class', grades__id=parent_id)
    elif level == 'subject':
        contents = model.objects.filter(type='class', subject__id=parent_id)
    elif level == 'chapter':
        contents = model.objects.filter(type='class', chapter__id=parent_id)
    elif level == 'subsection':
        contents = model.objects.filter(type='class', subsection__id=parent_id)
    else:
        return Response({'error': 'Invalid level. Must be one of: grade, subject, chapter, subsection.'}, status=400)

    # Make sure to eliminate duplicates (especially for M2M like grades)
    contents = contents.distinct()
    if any(content.ispaid == 'ispaid' for content in contents):  # Assuming the content has been fetched
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'Authentication required to access paid content.'}, status=401)
        
        # Check if user has valid subscription for at least one of the grades associated with the content
        grade = None
        if level == 'grade':
            grade = Grade.objects.get(id=parent_id)
        elif level == 'subject':
            subject = Subject.objects.get(id=parent_id)
            grade = subject.grade  # Get grade from related subject
        elif level == 'chapter':
            chapter = Chapter.objects.get(id=parent_id)
            grade = chapter.subject.grade  # Get grade from related subject
        elif level == 'subsection':
            subsection = Subsection.objects.get(id=parent_id)
            grade = subsection.chapter.subject.grade    
        if not grade:
            return Response({'error': 'Invalid level. Grade not found for the given content.'}, status=400)

        # 🧠 Only check subscriptions if the feature toggle is enabled
        if config and config.enable_subscription:
        # Now check if the user has a valid subscription for the extracted grade
            if not user_has_valid_subscription_for_grade(request.user, grade):
                return Response({'error': 'You do not have an active, valid subscription for this grade.'}, status=403)
    data = serializer_class(contents, many=True).data
    return Response({
        'level': level,
        'id': parent_id,
        'type': content_type,
        'results': data
    })


@api_view(['GET'])
def featured_subjects(request):
    grade_id = request.query_params.get('grade_id')

    if grade_id:
        try:
            grade = Grade.objects.get(id=grade_id)
        except Grade.DoesNotExist:
            return Response({'error': 'Grade not found'}, status=status.HTTP_404_NOT_FOUND)

        subjects = list(Subject.objects.filter(grade=grade))
        random.shuffle(subjects)
        selected_subjects = subjects[:3]

        serialized = SubjectSerializer(selected_subjects, many=True)
        return Response({

            'featured_subjects': serialized.data
        }, status=200)

    # If no grade_id is provided, return 3 random subjects across all grades
    subjects = list(Subject.objects.all())
    random.shuffle(subjects)
    selected_subjects = subjects[:3]

    serialized = SubjectSerializer(selected_subjects, many=True)

    return Response({

        'featured_subjects': serialized.data
    }, status=200)



@api_view(['POST'])
def submit_answer(request):
    question_id = request.data.get('question_id')
    exercise_id = request.data.get('exercise_id')
    user_answer = request.data.get('user_answer')

    if not all([question_id, exercise_id, user_answer is not None]):
        return Response({"error": "Missing question_id, exercise_id or user_answer"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        question = Question.objects.get(id=question_id)
    except Question.DoesNotExist:
        return Response({"error": "Question not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        exercise = Exercise.objects.get(id=exercise_id)
    except Exercise.DoesNotExist:
        return Response({"error": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)

    result = {
        "question_id": question_id,
        "exercise_id": exercise_id,
        "question_type": question.question_type,
    }

    selected_option = None
    answer_text = ""

    # Choose-type question
    if question.question_type == 'choose':
        correct_option = Option.objects.filter(question=question, is_correct=True).first()
        if not correct_option:
            return Response({"error": "No correct option set for this question"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if str(user_answer).isdigit():
            selected_option = Option.objects.filter(id=int(user_answer), question=question).first()
        else:
            selected_option = Option.objects.filter(text__iexact=user_answer.strip(), question=question).first()

        is_correct = selected_option and selected_option.id == correct_option.id

        result.update({
            "correct": is_correct,
            "correct_answer": correct_option.id,
            "selected_option": selected_option.id if selected_option else None,
        })

    # Write-type question
    elif question.question_type == 'write':
        expected = question.answer.strip().lower()
        answer_text = user_answer.strip()
        similarity = fuzz.ratio(answer_text.lower(), expected)
        is_correct = similarity >= 80

        result.update({
            "correct": is_correct,
            "similarity": similarity,
            "expected_answer": question.answer,
            "user_answer": answer_text
        })
    else:
        return Response({"error": "Unsupported question type"}, status=status.HTTP_400_BAD_REQUEST)
    user = request.user
    # ✅ Save Question Progress
    if(user.is_authenticated):
        QuestionProgress.objects.update_or_create(
            user=user,
            question=question,
            exercise=exercise,
            defaults={
                "selected_option": selected_option,
                "answer_text": answer_text,
            }
        )

        # ✅ Update Exercise Progress
        total_answered = QuestionProgress.objects.filter(user=user, exercise=exercise).count()

        ExerciseProgress.objects.update_or_create(
            user=user,
            exercise=exercise,
            defaults={
                "done_exercises": total_answered
            }
        )

    return Response(result, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsVerified])
def get_exercise_progress(request, exercise_id):
    user = request.user

    try:
        exercise = Exercise.objects.get(id=exercise_id)
    except Exercise.DoesNotExist:
        return Response({"error": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)

    questions = list(exercise.questions.order_by('rank'))
    progress_entries = QuestionProgress.objects.filter(user=user, exercise=exercise).select_related('question')

    progress_map = {p.question_id: p for p in progress_entries}
    progress_data = []

    for question in questions:
        p = progress_map.get(question.id)
        if not p:
            continue  # unanswered

        data = {
            "question_id": question.id,
            "answered_answer": p.selected_option_id if question.question_type == "choose" else p.answer_text,
        }

        if question.question_type == "choose":
            correct_option = question.options.filter(is_correct=True).first()
            data["correct_answer"] = correct_option.id if correct_option else None
            data["correct"] = p.selected_option_id == (correct_option.id if correct_option else None)

        elif question.question_type == "write":
            expected = question.answer.strip()
            user_answer = p.answer_text.strip()
            data["correct"] = fuzz.ratio(user_answer.lower(), expected.lower()) >= 80
            data["correct_answer"] = expected
            data["expected_answer"] = expected  # needed for showing explanation box

        progress_data.append(data)

    # Optional: resume index logic
    answered_ids = set(progress_map.keys())
    all_ids = [q.id for q in questions]
    resume_index = next((i for i, qid in enumerate(all_ids) if qid not in answered_ids), len(all_ids))

    return Response({
        "exercise_id": exercise_id,
        "progress": progress_data,
        "resume_index": resume_index,
        "completed": resume_index == len(all_ids),
    })
from rest_framework_simplejwt.tokens import AccessToken

from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()

@api_view(['GET'])
def protected_video_stream(request, video_id):
    video = get_object_or_404(Video, id=video_id)

    if video.ispaid == 'ispaid':
        grade = get_video_grade(video)
        token = request.GET.get("token")
        if not token:
            return Response({'error': 'Missing token'}, status=400)
        try:
            access = AccessToken(token)
            user_id = access["user_id"]
            user = User.objects.get(id=user_id)
            request.user = user  # ✅ Manually attach user to request
        except Exception as e:
            print("Invalid token:", e)
            return Response({'error': 'Invalid token'}, status=400)

        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required to access paid content.'}, status=401)

        if not user_has_valid_subscription_for_grade(request.user, grade):
            print("No valid subscription for user:", request.user.id)
            return Response({'error': 'You do not have an active, valid subscription for this grade.'}, status=403)

    file_path = video.video_file.path
    if not os.path.exists(file_path):
        return Http404("Video not found")

    response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"

    return response
@api_view(['GET'])
def protected_book_stream(request, book_id):
    """
    Securely serve or generate signed URLs for book PDFs stored on TeleCloud OBS.
    """
    book = get_object_or_404(Book, id=book_id)
    config = Configuration.objects.first()

    # 🔒 Paid-content validation
    if book.ispaid == 'ispaid' and (config and config.enable_subscription):
        grade = get_book_grade(book)
        token = request.GET.get("token")
        if not token or token == "null":
            return Response({'error': 'Missing or invalid token'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            access = AccessToken(token)
            user = User.objects.get(id=access["user_id"])
            request.user = user
        except Exception as e:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user_has_valid_subscription_for_grade(request.user, grade):
            return Response(
                {'error': 'You do not have an active, valid subscription for this grade.'},
                status=status.HTTP_403_FORBIDDEN
            )

    # ✅ Safe OBS handling — never use .path
    try:
        if not book.pdf_file:
            return Response({'error': 'Book file not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Generate temporary signed URL from OBS (django-storages handles signing)
        file_url = book.pdf_file.url

        # Option 1: Return signed URL (recommended)
        return Response({
            'id': book.id,
            'name': book.name,
            'url': file_url,
        }, status=status.HTTP_200_OK)

        # Option 2 (optional): Stream directly from OBS through Django
        # file_obj = book.pdf_file.open()
        # response = StreamingHttpResponse(file_obj, content_type='application/pdf')
        # response["Content-Disposition"] = f'inline; filename=\"{book.name}.pdf\"'
        # response["X-Content-Type-Options"] = "nosniff"
        # response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        # response["Pragma"] = "no-cache"
        # return response

    except Exception as e:
        print("OBS file access error:", e)
        return Response({'error': 'Error accessing file from OBS.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
def get_video_grade(video):
    """
    Dynamically resolve the grade for a video.
    Works whether grade is set directly or via subject/chapter/subsection.
    """
    if video.grade:
        return video.grade
    if video.subject and video.subject.grade:
        return video.subject.grade
    if video.chapter and video.chapter.subject and video.chapter.subject.grade:
        return video.chapter.subject.grade
    if video.subsection and video.subsection.chapter and video.subsection.chapter.subject:
        return video.subsection.chapter.subject.grade
    return None
def get_book_grade(book):
    """
    Dynamically resolve the grade for a book.
    Works whether grade is set directly or via subject/chapter/subsection.
    """
    if book.grade:
        return book.grade
    if book.subject and book.subject.grade:
        return book.subject.grade
    if book.chapter and book.chapter.subject and book.chapter.subject.grade:
        return book.chapter.subject.grade
    if book.subsection and book.subsection.chapter and book.subsection.chapter.subject:
        return book.subsection.chapter.subject.grade
    return None

import os
import re
import boto3
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import AccessToken
from django.conf import settings
from .models import Video


# 🔐 Reuse S3 client helper
def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        region_name=settings.AWS_S3_REGION_NAME,
    )


# ======================================================
# 🔑 Return encryption key (TeleCloud-hosted .key file)
# ======================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def get_video_key(request, video_id):
    """Return encryption key for a video, with access check if paid."""
    video = get_object_or_404(Video, id=video_id)
    config = Configuration.objects.first()

    # ✅ Access control for paid videos
    if video.ispaid == "ispaid" and (config and config.enable_subscription):
        token = request.GET.get("token")
        if not token or token in ["null", "undefined", ""]:
            return Response({"error": "Missing or invalid token"}, status=400)

        try:
            access = AccessToken(token)
            user = User.objects.get(id=access["user_id"])
        except Exception as e:
            print("Invalid token:", e)
            return Response({"error": "Invalid token"}, status=400)

        if not user_has_valid_subscription_for_grade(user, video.grade):
            raise PermissionDenied("You do not have a valid subscription for this grade.")

    # ✅ Ensure key exists
    if not video.encryption_key:
        raise Http404("Encryption key not found")

    s3 = get_s3_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    key_path = video.encryption_key.name

    # ✅ Generate a presigned URL to read the key file
    try:
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key_path},
            ExpiresIn=60,  # 1 minute — just long enough for the player to fetch
        )
    except Exception as e:
        print(" Failed to generate presigned URL:", e)
        raise Http404("Encryption key not accessible")

    # Return the raw key file directly
    response = HttpResponse(content_type="application/octet-stream")
    response["Content-Disposition"] = "inline"
    response["Cache-Control"] = "no-store"
    response["X-Redirect-URL"] = presigned_url  # optional debug info
    return response


# ======================================================
# 🎬 Return playlist (.m3u8) with TeleCloud URLs
# ======================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def get_video_playlist(request, video_id):
    """
    Return the HLS playlist (.m3u8) with:
    - Secure key URL for paid content
    - Presigned OBS URLs for all segments
    """
    video = get_object_or_404(Video, id=video_id)
    token = request.GET.get("token")
    config = Configuration.objects.first()

    if not video.hls_playlist:
        raise Http404("Playlist not found")

    # 🔗 Fetch playlist text from TeleCloud
    s3 = get_s3_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    playlist_key = video.hls_playlist.name

    try:
        playlist_obj = s3.get_object(Bucket=bucket, Key=playlist_key)
        playlist_content = playlist_obj["Body"].read().decode("utf-8")
    except Exception as e:
        print(" Failed to fetch playlist from OBS:", e)
        raise Http404("Playlist not accessible")

    # ✅ Replace key URI
    if video.ispaid == "ispaid" and (config and config.enable_subscription):
        if not token or token in ["null", "undefined", ""]:
            return Response({"error": "Missing or invalid token"}, status=400)
        secure_key_url = request.build_absolute_uri(f"/api/contents/key/{video.id}/?token={token}")
    else:
        # Free video: use direct OBS presigned key URL
        try:
            secure_key_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": video.encryption_key.name},
                ExpiresIn=3600,
            )
        except Exception as e:
            print(" Could not generate key URL:", e)
            secure_key_url = ""

    playlist_content = re.sub(r'URI=\".*?\"', f'URI="{secure_key_url}"', playlist_content)

    # ✅ Replace each .ts segment with presigned URLs
    def segment_replacer(match):
        segment_name = os.path.basename(match.group(2))
        segment_key = f"videos/hls/{video.id}_{video.title.replace(' ', '_')}/segments/{segment_name}"
        try:
            presigned = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": segment_key},
                ExpiresIn=3600,
            )
        except Exception as e:
            print(f" Could not generate segment URL for {segment_name}: {e}")
            presigned = f"/media/{segment_key}"  # fallback
        return f"\n{presigned}"

    playlist_content = re.sub(r'(^|\n)(?:\.\./segments/)?(out_\d+\.ts)', segment_replacer, playlist_content)

    # ✅ Return playlist
    response = HttpResponse(playlist_content, content_type="application/vnd.apple.mpegurl;charset=utf-8")
    response["Content-Disposition"] = "inline"
    response["Cache-Control"] = "no-store"
    return response




