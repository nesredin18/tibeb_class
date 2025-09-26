# notifications/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from contents.models import Book, Video, Exercise
from user.models import User_Grade
from .models import Notification

def get_related_users(instance):
    """Return users whose grades match the content level."""
    if instance.subsection:
        grade = instance.subsection.chapter.subject.grade
    elif instance.chapter:
        grade = instance.chapter.subject.grade
    elif instance.subject:
        grade = instance.subject.grade
    elif hasattr(instance, 'grade') and instance.grade:
        grade = instance.grade
    else:
        grade = None

    if grade:
        return [ug.user for ug in User_Grade.objects.filter(grade=grade, is_active=True)]
    return []


@receiver(post_save, sender=Book)
@receiver(post_save, sender=Video)
@receiver(post_save, sender=Exercise)
def send_content_notification(sender, instance, created, **kwargs):
    if not created:
        return

    users = get_related_users(instance)
    if not users:
        return

    content_type = sender.__name__.lower()  # e.g., 'book', 'video', 'exercise'
    message = f"New {content_type.title()} released: {getattr(instance, 'name', getattr(instance, 'title', 'Untitled'))}"

    notifications = [
        Notification(user=user, content_type=content_type, content_id=instance.id, message=message)
        for user in users
    ]
    Notification.objects.bulk_create(notifications)

    # 🔴 OPTIONAL: trigger real-time notification
    from .utils import send_realtime_notification
    for user in users:
        send_realtime_notification(user.id, message)
