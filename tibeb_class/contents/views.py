from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Grade, Subject, Book, Chapter, Subsection, Exercise, Video
from .serializers import GradeSerializer, SubjectSerializer, BookSerializer, ChapterSerializer, SubsectionSerializer, ExerciseSerializer, VideoSerializer,SubjectMiniSerializer
import random

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
        'chapter_title': chapter.title,
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
@api_view(['GET'])
def featured_subjects(request):
    grade_id = request.query_params.get('grade_id')

    if grade_id:
        try:
            grade = Grade.objects.get(id=grade_id)
        except Grade.DoesNotExist:
            return Response({'error': 'Grade not found'}, status=status.HTTP_404_NOT_FOUND)

        subjects = Subject.objects.filter(grade=grade)[:3]
        serialized = SubjectMiniSerializer(subjects, many=True)
        return Response({
            'grade_id': grade.id,
            'grade_name': grade.name,
            'featured_subjects': serialized.data
        }, status=200)

    # If no grade_id is provided, return 3 random subjects across all grades
    subjects = list(Subject.objects.all())
    random.shuffle(subjects)
    selected_subjects = subjects[:3]

    serialized = SubjectMiniSerializer(selected_subjects, many=True)

    return Response({
        'grade_id': None,
        'grade_name': None,
        'featured_subjects': serialized.data
    }, status=200)