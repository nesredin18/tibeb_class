from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Grade, Subject, Book, Chapter, Subsection, Exercise, Video
from .serializers import GradeSerializer, SubjectSerializer, BookSerializer, ChapterSerializer, SubsectionSerializer, ExerciseSerializer, VideoSerializer

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
def get_subsections(request):
    subsections = Subsection.objects.all()
    serializer = SubsectionSerializer(subsections, many=True)
    return Response(serializer.data)

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
