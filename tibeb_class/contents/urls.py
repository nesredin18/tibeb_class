from django.urls import path
from .views import (
    get_grades, get_subjects, get_books, get_chapters, get_subsections,
    get_exercises, get_videos
)

urlpatterns = [
    path('grades/', get_grades, name='get-grades'),
    path('subjects/', get_subjects, name='get-subjects'),
    path('books/', get_books, name='get-books'),
    path('chapters/', get_chapters, name='get-chapters'),
    path('subsections/', get_subsections, name='get-subsections'),
    path('exercises/', get_exercises, name='get-exercises'),
    path('videos/', get_videos, name='get-videos'),

]