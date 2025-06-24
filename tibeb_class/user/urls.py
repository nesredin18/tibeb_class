from django.urls import path
from .views import signup, login, test
from .views import get_user_info, get_pending_requests, get_accepted_requests, get_progress
from .views import create_user_subscription, get_active_subscription,update_progress,aggregated_progress_chapter_level
from .views import start_grade,user_grade,aggregated_progress_per_grade,aggregated_progress_chapter_level,aggregated_progress_subject_level,aggregated_progress_subsection_level
from .views import subsection_progress_summary,update_user,get_user_info


urlpatterns = [
    path('signup/', signup, name='signup'),
    path('update/', update_user, name='update-user'),
    path('login/', login, name='login'),
    path('',get_user_info, name='user-info'),
    path('test/', test, name='test'),
    path('user/info/', get_user_info, name='user-info'),
    path('student/parent-requests/', get_pending_requests, name='parent-requests'),
    path('student/accepted-requests/', get_accepted_requests, name='accepted-requests'),
    path('student/progress/', get_progress, name='student-progress'),
    path('student/update-progress/', update_progress, name='update-progress'),
    path('student/create-subscription/', create_user_subscription, name='create-subscription'),
    path('student/active-subscription/', get_active_subscription, name='active-subscription'),
    path('student/start-grade/', start_grade, name='start-grade'),
    path('student/user-grade/', user_grade, name='user-grade'),
    path('student/aggregated-progress/per-grade/', aggregated_progress_per_grade, name='aggregated-progress-per-grade'),
    path('student/aggregated-progress/subject-level/', aggregated_progress_subject_level, name='aggregated-progress-subject-level'),
    path('student/aggregated-progress/chapter-level/', aggregated_progress_chapter_level, name='aggregated-progress-chapter-level'),
    path('student/aggregated-progress/subsection-level/', aggregated_progress_subsection_level, name='aggregated-progress-subsection-level'),
    path('student/subsection-progress-summary/', subsection_progress_summary, name='subsection-progress-summary'),
]
