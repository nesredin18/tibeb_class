from django.urls import path
from .views import (
    get_announcements, get_exercise_progress, get_grades, get_subjects, get_books, get_chapters, get_subsections,
    get_exercises, get_videos,featured_subjects, protected_book_stream, protected_video_stream,subjects_by_grade,
    chapters_by_subject, subsections_by_chapter,
    get_chapter_by_id, get_subsection_by_id,get_content_by_type_and_level,get_video_key,get_exercise_question,submit_answer,get_video_playlist,get_video_key
)

urlpatterns = [
    path('announcements/', get_announcements, name='get-announcements'),
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
    path("key/<int:video_id>/", get_video_key, name="get_video_key"),
    path('exercise/<int:exercise_id>/question/', get_exercise_question, name='get_exercise_question'),
    path('submit-answer/', submit_answer, name='submit-answer'),
    path('exercise/<int:exercise_id>/progress/', get_exercise_progress, name='exercise-progress'),
    path("secure-video/<int:video_id>/", protected_video_stream, name="secure_video"),
    path("secure-book/<int:book_id>/", protected_book_stream, name="secure_book"),
    path('video/<int:video_id>/playlist/', get_video_playlist, name='get_video_playlist'),

]
from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
