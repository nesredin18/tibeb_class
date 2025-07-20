from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from moviepy import VideoFileClip
from datetime import timedelta
from .models import Video
import os
from .models import Book
import fitz  # PyMuPDF

@receiver(post_save, sender=Video)
def extract_duration(sender, instance, created, **kwargs):
    if instance.video_file and instance.video_file.path:
        try:
            video_path = instance.video_file.path
            if os.path.exists(video_path):
                clip = VideoFileClip(video_path)
                duration = timedelta(seconds=int(clip.duration))
                clip.close()  # Release file before further action

                if instance.duration != duration:
                    # Avoid recursive signal calls
                    Video.objects.filter(pk=instance.pk).update(duration=duration)

        except Exception as e:
            print(f"Error extracting video duration: {e}")


# Extract total pages only if new or changed
@receiver(post_save, sender=Book)
def extract_pdf_page_count(sender, instance, created, **kwargs):
    if instance.pdf_file and instance.pdf_file.path:
        try:
            with fitz.open(instance.pdf_file.path) as doc:
                total_pages = doc.page_count
                if instance.total_pages != total_pages:
                    instance.total_pages = total_pages
                    # Avoid recursion loop if already in save
                    Book.objects.filter(pk=instance.pk).update(total_pages=total_pages)
        except Exception as e:
            print(f"Error extracting PDF pages: {e}")

