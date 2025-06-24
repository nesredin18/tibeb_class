from django.urls import path
from .views import (
    get_grades, get_subjects, get_books, get_chapters, get_subsections,
    get_exercises, get_videos,featured_subjects,subjects_by_grade,
    chapters_by_subject, subsections_by_chapter
)

urlpatterns = [
    path('grades/', get_grades, name='get-grades'),
    path('grades/<int:grade_id>/subjects/', subjects_by_grade, name='subjects-by-grade'),
    path('subjects/', get_subjects, name='get-subjects'),
    path('books/', get_books, name='get-books'),
    path('chapters/', get_chapters, name='get-chapters'),
    path('subsections/', get_subsections, name='get-subsections'),
    path('exercises/', get_exercises, name='get-exercises'),
    path('videos/', get_videos, name='get-videos'),
    path('featured-subjects/', featured_subjects, name='featured-subjects'),
    path('subjects/<int:subject_id>/chapters/', chapters_by_subject, name='chapters-by-subject'),
    path('chapters/<int:chapter_id>', subsections_by_chapter, name='subsections-by-chapter'),

]