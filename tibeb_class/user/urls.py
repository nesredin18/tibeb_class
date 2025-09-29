from django.urls import path
from .views import change_password, reset_password, send_password_reset_code, signup, login, test,verify_username
from .views import get_user_info, get_pending_requests, get_accepted_requests
from .views import aggregated_progress_chapter_level
from .views import start_grade,user_grade,aggregated_progress_per_grade,aggregated_progress_chapter_level,aggregated_progress_subject_level,aggregated_progress_subsection_level
from .views import update_user,get_user_info, add_child_account, respond_to_parent_request
from .views import get_parent_childs,get_child_requests,cancel_child_request,unlink_child
from .views import get_user_progress,track_book_progress,track_video_progress,aggregated_progress_subjects_under_user_grades,aggregated_progress_chapter_level_for_user,resend_verification_code
from .views import reset_question_progress_for_exercise,verify_password_reset_code,request_username_change,confirm_username_change
from .views import resend_request_username_change
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,  # optional
)
urlpatterns = [
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),         # refresh
    path('signup/', signup, name='signup'),
    path('verify-username/', verify_username, name='verify-username'),
    path('verify-password/', verify_password_reset_code, name='verify-password'),
    path('send-password-reset/', send_password_reset_code, name='password-reset-email'),
    path('reset-password/<uidb64>/<token>/', reset_password, name='reset-password'),
    path('change-password/', change_password, name='change-password'),
    path('resend-varification/', resend_verification_code, name='resend-varification'),
    path('update-email/', request_username_change, name='update_email_and_send_verification'),
    path('confirm-update-email/', confirm_username_change, name='confirm_update_email'),
    path('resend-update-email/', resend_request_username_change, name='resend_request_username_change'),
    path('reset-exercise/', reset_question_progress_for_exercise, name='reset_question_progress_for_exercise'),
    path('update/', update_user, name='update-user'),
    path('login/', login, name='login'),
    path('',get_user_info, name='user-info'),
    path('add-child-account/', add_child_account, name='add-child-account'),
    path('test/', test, name='test'),
    path('user/info/', get_user_info, name='user-info'),
    path('parent/cancel-child-request/', cancel_child_request, name='cancel-child-request'),
    path('parent/unlink-child/', unlink_child, name='unlink-child'),
    path('parent/childs/', get_parent_childs, name='parent-childs'),
    path('parent/child-requests/', get_child_requests, name='child-requests'),
    path('student/respond-to-parent-request/', respond_to_parent_request, name='respond-to-parent-request'),
    path('student/parent-requests/', get_pending_requests, name='parent-requests'),
    path('student/accepted-requests/', get_accepted_requests, name='accepted-requests'),
    path('student/update-book-progress/', track_book_progress, name='track_book_progress'),
    path('student/update-video-progress/', track_video_progress, name='track_video_progress'),
    path('student/start-grade/', start_grade, name='start-grade'),
    path('student/user-grade/', user_grade, name='user-grade'),
    path('student/user-progress/<str:content_type>/<int:content_id>/', get_user_progress, name='get_user_progress'),
    path('student/aggregated-progress/per-grade/', aggregated_progress_per_grade, name='aggregated-progress-per-grade'),
    path('student/aggregated-progress/subject-level/', aggregated_progress_subject_level, name='aggregated-progress-subject-level'),
    path('student/aggregated-progress/summery-subject-level/', aggregated_progress_subjects_under_user_grades, name='aggregated_progress_subjects_under_user_grades'),
    path('student/aggregated-progress/chapter-level/', aggregated_progress_chapter_level, name='aggregated-progress-chapter-level'),
    path('student/aggregated-progress/summery-chapter-level/', aggregated_progress_chapter_level_for_user, name='aggregated_progress_chapter_level_for_user'),
    path('student/aggregated-progress/subsection-level/', aggregated_progress_subsection_level, name='aggregated-progress-subsection-level'),
]
