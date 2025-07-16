import os
from django.conf import settings
from django.http import FileResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Grade, Subject, Book, Chapter, Subsection, Exercise, Video
from .serializers import GradeSerializer, SubjectSerializer, BookSerializer, ChapterSerializer, SubsectionSerializer, ExerciseSerializer, VideoSerializer,SubjectMiniSerializer
import random

@api_view(['GET'])
def get_video_key(request):
    video_id = request.GET.get('video_id')
    key_path = os.path.join(settings.MEDIA_ROOT, f"keys/video_{video_id}.key")

    if not os.path.exists(key_path):
        return Response({'error': 'id not found'}, status=status.HTTP_404_NOT_FOUND)

    return FileResponse(open(key_path, 'rb'), content_type='application/octet-stream')
@api_view(['GET'])
def get_grades(request):
    grades = Grade.objects.all()
    serializer = GradeSerializer(grades, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_subjects(request):
    subjects = Subject.objects.all()
    serializer = SubjectSerializer(subjects, many=True)
    return Response(serializer.data)
@api_view(['GET'])
def subjects_by_grade(request, grade_id):
    try:
        grade = Grade.objects.get(id=grade_id)
    except Grade.DoesNotExist:
        return Response({'error': 'Grade not found'}, status=status.HTTP_404_NOT_FOUND)

    subjects = Subject.objects.filter(grade=grade)
    serializer = SubjectSerializer(subjects, many=True)

    return Response({
        'grade_id': grade.id,
        'grade_name': grade.name,
        'subjects': serializer.data
    }, status=200)

@api_view(['GET'])
def get_books(request):
    books = Book.objects.all()
    serializer = BookSerializer(books, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_chapters(request):
    chapters = Chapter.objects.all()
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

    chapters = Chapter.objects.filter(subject=subject)
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
    subsections = Subsection.objects.all()
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

    subsections = Subsection.objects.filter(chapter=chapter)
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
    exercises = Exercise.objects.all()
    serializer = ExerciseSerializer(exercises, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_videos(request):
    videos = Video.objects.all()
    serializer = VideoSerializer(videos, many=True)
    return Response(serializer.data)
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from django.db.models import Q

@api_view(['GET'])
def get_content_by_type_and_level(request):
    content_type = request.query_params.get('type')        # 'video', 'book', 'exercise'
    level = request.query_params.get('level')              # 'grade', 'subject', etc.
    parent_id = request.query_params.get('id')

    if not content_type or not level or not parent_id:
        return Response({'error': 'Parameters "type", "level", and "id" are required.'}, status=400)

    try:
        parent_id = int(parent_id)
    except ValueError:
        return Response({'error': '"id" must be an integer.'}, status=400)

    # Import your models

    # Prepare lookups
    if level == 'grade':
        grade = Grade.objects.filter(id=parent_id).first()
        if not grade:
            return Response({'error': 'Grade not found.'}, status=404)
        subjects = Subject.objects.filter(grade=grade)
        chapters = Chapter.objects.filter(subject__in=subjects)
        subsections = Subsection.objects.filter(chapter__in=chapters)
        grade_q = Q(grade=grade)
        subject_q = Q(subject__in=subjects)
        chapter_q = Q(chapter__in=chapters)
        subsection_q = Q(subsection__in=subsections)

    elif level == 'subject':
        subject = Subject.objects.filter(id=parent_id).first()
        if not subject:
            return Response({'error': 'Subject not found.'}, status=404)
        chapters = Chapter.objects.filter(subject=subject)
        subsections = Subsection.objects.filter(chapter__in=chapters)
        grade_q = Q()
        subject_q = Q(subject=subject)
        chapter_q = Q(chapter__in=chapters)
        subsection_q = Q(subsection__in=subsections)

    elif level == 'chapter':
        chapter = Chapter.objects.filter(id=parent_id).first()
        if not chapter:
            return Response({'error': 'Chapter not found.'}, status=404)
        subsections = Subsection.objects.filter(chapter=chapter)
        grade_q = Q()
        subject_q = Q()
        chapter_q = Q(chapter=chapter)
        subsection_q = Q(subsection__in=subsections)

    elif level == 'subsection':
        subsection = Subsection.objects.filter(id=parent_id).first()
        if not subsection:
            return Response({'error': 'Subsection not found.'}, status=404)
        grade_q = Q()
        subject_q = Q()
        chapter_q = Q()
        subsection_q = Q(subsection=subsection)

    else:
        return Response({'error': 'Invalid level. Must be one of: grade, subject, chapter, subsection.'}, status=400)

    # Apply filters
    if content_type == 'video':
        contents = Video.objects.filter(
            type='class'
        ).filter(
            grade_q | subject_q | chapter_q | subsection_q
        )
        data = VideoSerializer(contents, many=True).data

    elif content_type == 'book':
        contents = Book.objects.filter(
            type='class'
        ).filter(
            grade_q | subject_q | chapter_q | subsection_q
        )
        data = BookSerializer(contents, many=True).data

    elif content_type == 'exercise':
        contents = Exercise.objects.filter(
            type='class'
        ).filter(
            Q(grades=parent_id) | subject_q | chapter_q | subsection_q
        ).distinct()
        data = ExerciseSerializer(contents, many=True).data

    else:
        return Response({'error': 'Invalid type. Must be one of: video, book, exercise.'}, status=400)

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

        subjects = Subject.objects.filter(grade=grade)[:3]
        serialized = SubjectSerializer(subjects, many=True)
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