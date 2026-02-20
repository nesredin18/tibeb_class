from apscheduler.schedulers.background import BackgroundScheduler
from django.apps import apps
from django.db import transaction
from .models import NotificationQueue, Notification
from user.models import User_Grade, CustomUser
from .utils import send_realtime_notification, send_firebase_notification

CONTENT_MODELS = {
    "book": "contents.Book",
    "video": "contents.Video",
    "exercise": "contents.Exercise",
}


def distribute_notifications():
    """Distribute queued notifications, then delete queue items."""
    for item in NotificationQueue.objects.iterator(chunk_size=100):
        user_ids = list(
            User_Grade.objects
            .filter(grade_id=item.content_grade_id, is_active=True)
            .values_list("user_id", flat=True)
        )

        if not user_ids:
            item.delete()
            continue

        users_map = {
            user.id: user
            for user in CustomUser.objects.filter(id__in=user_ids).only("id", "fcm_token")
        }

        with transaction.atomic():
            Notification.objects.bulk_create(
                [
                    Notification(
                        user_id=uid,
                        content_type=item.content_type,
                        content_id=item.content_id,
                        message=item.message,
                        target_grade_id=item.target_grade_id,
                        target_subject_id=item.target_subject_id,
                        target_chapter_id=item.target_chapter_id,
                        target_subsection_id=item.target_subsection_id,
                        type=item.type,
                        level=item.level,
                    )
                    for uid in user_ids
                ],
                batch_size=1000,
            )

            for uid in user_ids:
                 try:
                     send_realtime_notification(uid, item.message)
                 except Exception as e:
                     print(f" WS send failed for user {uid}: {e}")

                 try:
                     user = users_map.get(uid)
                     if user:
                         send_firebase_notification(
                             user=user,
                             title="Tibeb Class",
                             body=item.message,
                             data={
                                 "content_type": item.content_type,
                                 "content_id": item.content_id,
                                 "target_grade_id": item.target_grade_id,
                                 "target_subject_id": item.target_subject_id,
                                 "target_chapter_id": item.target_chapter_id,
                                 "target_subsection_id": item.target_subsection_id,
                                 "level": item.level,
                                 "type": item.type,
                             },
                         )
                 except Exception as e:
                     print(f" FCM send failed for user {uid}: {e}")

            item.delete()




