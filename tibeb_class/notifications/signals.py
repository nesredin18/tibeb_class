# notifications/signals.py
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from contents.models import Book, Video, Exercise
from .models import NotificationQueue


def _title_of(instance):
    return getattr(instance, "name", getattr(instance, "title", "Untitled"))


def _derive_hierarchy(instance):
    """
    Returns (grade_id, subject_id, chapter_id, subsection_id, level)
    Exactly one of the hierarchy foreign keys is set on the content.
    We fill the rest by traversing relations.
    """
    grade_id = subject_id = chapter_id = subsection_id = None
    level = "grade"

    if getattr(instance, "subsection_id", None):
        subsection_id = instance.subsection_id
        chapter_id = instance.subsection.chapter_id
        subject_id = instance.subsection.chapter.subject_id
        grade_id = instance.subsection.chapter.subject.grade_id
        level = "subsection"
    elif getattr(instance, "chapter_id", None):
        chapter_id = instance.chapter_id
        subject_id = instance.chapter.subject_id
        grade_id = instance.chapter.subject.grade_id
        level = "chapter"
    elif getattr(instance, "subject_id", None):
        subject_id = instance.subject_id
        grade_id = instance.subject.grade_id
        level = "subject"
    elif getattr(instance, "grade_id", None):
        grade_id = instance.grade_id
        level = "grade"

    return grade_id, subject_id, chapter_id, subsection_id, level


# -------------------------
# Book & Video via post_save
# -------------------------
@receiver(post_save, sender=Book)
@receiver(post_save, sender=Video)
def enqueue_notification_for_book_video(sender, instance, created, **kwargs):
    if not created:
        return

    message = f"New {sender.__name__} released: {_title_of(instance)}"
    resource_type = getattr(instance, "type", "class")  # 'class' or 'additional'
    content_type = "book" if sender is Book else "video"

    grade_id, subject_id, chapter_id, subsection_id, level = _derive_hierarchy(instance)

    NotificationQueue.objects.create(
        content_type=content_type,
        content_id=instance.id,
        message=message,
        content_grade_id=grade_id,
        target_grade_id=grade_id,
        target_subject_id=subject_id,
        target_chapter_id=chapter_id,
        target_subsection_id=subsection_id,
        type=resource_type,
        level=level,
    )

    print(f"🕒 Queued notification for {sender.__name__} '{_title_of(instance)}' → Grade {grade_id} (level={level})")


# ------------------------------------
# Exercise grades via m2m_changed hook
# ------------------------------------
@receiver(m2m_changed, sender=Exercise.grades.through)
def enqueue_notification_for_exercise_grades(sender, instance, action, pk_set, **kwargs):
    """
    Called when grades are added to an Exercise (after the M2M rows exist).
    We enqueue one queue item per grade in pk_set.
    """
    if action != "post_add":
        return

    if not pk_set:
        return

    message = f"New Exercise released: {_title_of(instance)}"
    resource_type = getattr(instance, "type", "class")
    content_type = "exercise"

    # Derive the rest of the hierarchy from the single pointer provided on the exercise
    grade_id, subject_id, chapter_id, subsection_id, level_from_fk = _derive_hierarchy(instance)

    # For exercises with explicit grades, we always target 'grade' level in the queue
    for g_id in pk_set:
        NotificationQueue.objects.create(
            content_type=content_type,
            content_id=instance.id,
            message=message,
            content_grade_id=g_id,      # concrete grade this queue item targets
            target_grade_id=g_id,        # same as content_grade_id
            target_subject_id=subject_id,
            target_chapter_id=chapter_id,
            target_subsection_id=subsection_id,
            type=resource_type,
            level="grade",               # explicit M2M means per-grade targeting
        )

    print(f"🕒 Queued notifications for Exercise '{_title_of(instance)}' → Grades {sorted(pk_set)} (level=grade)")


# ---------------------------------------------------
# (Optional) Exercise without grades on save fallback
# ---------------------------------------------------
@receiver(post_save, sender=Exercise)
def enqueue_notification_for_exercise_no_grades(sender, instance, created, **kwargs):
    """
    If an Exercise is created without grades initially, we don't enqueue here.
    We rely on m2m_changed when grades are added.
    However, if you want to handle the edge case where an exercise targets a specific
    chapter/subsection but has no M2M grades at all, uncomment the block below.
    """
    if not created:
        return



    # # --- Uncomment to enqueue a single derived grade when there are no M2M grades ---
    if not instance.grades.exists():
         message = f"New Exercise released: {_title_of(instance)}"
         resource_type = getattr(instance, "type", "class")
         content_type = "exercise"
         grade_id, subject_id, chapter_id, subsection_id, level = _derive_hierarchy(instance)
         if grade_id:
             NotificationQueue.objects.create(
                 content_type=content_type,
                 content_id=instance.id,
                 message=message,
                 content_grade_id=grade_id,
                 target_grade_id=grade_id,
                 target_subject_id=subject_id,
                 target_chapter_id=chapter_id,
                 target_subsection_id=subsection_id,
                 type=resource_type,
                 level=level,
             )
             print(f"🕒 Queued notification for Exercise '{_title_of(instance)}' → Grade {grade_id} (level={level})")
