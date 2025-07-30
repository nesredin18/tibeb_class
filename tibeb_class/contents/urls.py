from django.urls import path
from .views import (
    get_grades, get_subjects, get_books, get_chapters, get_subsections,
    get_exercises, get_videos,featured_subjects,subjects_by_grade,
    chapters_by_subject, subsections_by_chapter,
    get_chapter_by_id, get_subsection_by_id,get_content_by_type_and_level,get_video_key,get_exercise_question
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
    path('chapters/<int:chapter_id>/subsections', subsections_by_chapter, name='subsections-by-chapter'),
    path('chapters/<int:chapter_id>/', get_chapter_by_id, name='get-chapter-by-id'),
    path('subsections/<int:subsection_id>/', get_subsection_by_id, name='get-subsection-by-id'),
    path('get-content/',get_content_by_type_and_level,name='get_content_by_type_and_level'),
    path("get-key/", get_video_key, name="get_video_key"),
    path('exercise/<int:exercise_id>/question/', get_exercise_question, name='get_exercise_question'),


]
from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)