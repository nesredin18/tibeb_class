import zipfile
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from moviepy import VideoFileClip
from datetime import timedelta

from tibeb_class import settings
from .models import Video
import os
from .models import Book
import fitz
from django.db.models.signals import m2m_changed
from .models import Question
import subprocess
import json
import shutil
import re
@receiver(post_save, sender=Video)
def extract_hls_duration(sender, instance, created, **kwargs):
    """
    Automatically compute HLS video duration using ffprobe.
    Fixes both key and segment paths for encrypted playlists.
    """
    if not instance.hls_playlist:
        return

    playlist_path = instance.hls_playlist.path
    if not os.path.exists(playlist_path):
        print(f"⚠️ Playlist not found: {playlist_path}")
        return

    playlist_dir = os.path.dirname(playlist_path)
    base_dir = os.path.dirname(playlist_dir)  # parent folder: .../<id_title>/
    segments_dir = os.path.join(base_dir, "segments")
    keys_dir = os.path.join(base_dir, "keys")
    temp_playlist_path = os.path.join(playlist_dir, "_temp_for_probe.m3u8")

    try:
        with open(playlist_path, "r", encoding="utf-8") as f:
            content = f.read()

        # ✅ Fix encryption key path (if present)
        if 'EXT-X-KEY' in content:
            key_path = os.path.join(keys_dir, "encryption.key")
            abs_key_path = os.path.abspath(key_path).replace("\\", "/")
            fixed_key_uri = f'URI="file:{abs_key_path}"'
            content = re.sub(r'URI=\".*?\"', fixed_key_uri, content)

        # ✅ Fix segment paths (relative → absolute)
        def replace_segment(match):
            segment_name = os.path.basename(match.group(2))
            abs_segment = os.path.abspath(os.path.join(segments_dir, segment_name)).replace("\\", "/")
            return f"\nfile:{abs_segment}"

        content = re.sub(r'(^|\n)(\.\./segments/out_\d+\.ts|out_\d+\.ts)', replace_segment, content)

        # ✅ Save temporary playlist
        with open(temp_playlist_path, "w", encoding="utf-8") as f:
            f.write(content)

        # ✅ Run ffprobe (allowing crypto protocol)
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-allowed_extensions", "ALL",
                "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                "-show_entries", "format=duration",
                "-of", "json",
                temp_playlist_path,
            ],
            cwd=playlist_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

        info = json.loads(result.stdout or "{}")
        total_seconds = float(info.get("format", {}).get("duration", 0))

        if total_seconds <= 0:
            return

        duration = timedelta(seconds=int(total_seconds))
        if instance.duration != duration:
            Video.objects.filter(pk=instance.pk).update(duration=duration)


    except subprocess.CalledProcessError as e:
        print(f"❌ ffprobe failed for {instance.title}: {e.stderr}")
    except Exception as e:
        print(f"❌ Error extracting duration for {instance.title}: {e}")
    finally:
        if os.path.exists(temp_playlist_path):
            os.remove(temp_playlist_path)

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

@receiver(m2m_changed, sender=Question.exercises.through)
def update_total_exercises(sender, instance, action, reverse, model, pk_set, **kwargs):
    # If reverse is False, instance is a Question; otherwise, it's an Exercise
    if action in ["post_add", "post_remove", "post_clear"]:
        if reverse:
            # instance is Exercise
            exercise = instance
            total = exercise.questions.count()
            exercise.total_exercise = total
            exercise.save(update_fields=["total_exercise"])
        else:
            # instance is Question, update all related exercises
            for exercise in instance.exercises.all():
                total = exercise.questions.count()
                exercise.total_exercise = total
                exercise.save(update_fields=["total_exercise"])

import os
import zipfile
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Video

@receiver(post_save, sender=Video)
def extract_hls_files(sender, instance, created, **kwargs):
    """
    Handles automatic extraction of uploaded HLS ZIP files.
    - Extracts .ts segments and related files
    - Deletes the ZIP file after extraction
    - If re-uploaded (update), replaces old extracted segments with new ones
    - If no ZIP file provided, keeps existing segments unchanged
    """
    if not instance.segments_zip:
        # ✅ No new zip file uploaded → keep existing segments unchanged
        return

    # ✅ Prepare base folders
    video_dir = os.path.join('media/videos/hls', f"{instance.id}_{instance.title.replace(' ', '_')}")
    segments_dir = os.path.join(video_dir, 'segments')
    playlists_dir = os.path.join(video_dir, 'playlist')
    keys_dir = os.path.join(video_dir, 'keys')

    os.makedirs(segments_dir, exist_ok=True)
    os.makedirs(playlists_dir, exist_ok=True)
    os.makedirs(keys_dir, exist_ok=True)

    zip_path = instance.segments_zip.path

    try:
        # ✅ If there are old segments, remove them (only if replacing with new ZIP)
        if os.path.exists(segments_dir):
            for item in os.listdir(segments_dir):
                item_path = os.path.join(segments_dir, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)

        # ✅ Extract ZIP
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Detect if the ZIP already contains "segments/"
            top_level_names = {name.split('/')[0] for name in zip_ref.namelist() if '/' in name}
            if "segments" in top_level_names:
                # Extract only inside "segments/" folder
                for member in zip_ref.namelist():
                    if member.startswith("segments/"):
                        zip_ref.extract(member, video_dir)

                # Move extracted files up one level
                inner_dir = os.path.join(video_dir, "segments")
                for filename in os.listdir(inner_dir):
                    src = os.path.join(inner_dir, filename)
                    dst = os.path.join(segments_dir, filename)
                    if os.path.isfile(src):
                        os.replace(src, dst)
                # Remove temporary nested "segments/" folder
                try:
                    os.rmdir(inner_dir)
                except OSError:
                    pass
            else:
                # Extract directly to segments folder
                zip_ref.extractall(segments_dir)


        # ✅ Delete ZIP after extraction
        if os.path.exists(zip_path):
            os.remove(zip_path)

        # ✅ Clear ZIP field from database
        instance.segments_zip.delete(save=False)
        instance.segments_zip = None
        instance.save(update_fields=['segments_zip'])

    except Exception as e:
        print(f"❌ Failed to extract zip for {instance.title}: {e}")




@receiver(post_save, sender=Video)
def move_video_files(sender, instance, created, **kwargs):
    """
    Move uploaded HLS playlist (.m3u8) and key file to their permanent
    per-video directories once ID exists.
    
    ✅ Handles both new uploads and updates:
        - Moves new files to the correct folders
        - Replaces old playlist/key if new versions are uploaded
        - Skips moving if no new files are uploaded
    """
    if not instance.id:
        return

    # ✅ Define base folders using MEDIA_ROOT
    base_dir = os.path.join(settings.MEDIA_ROOT, "videos", "hls", f"{instance.id}_{instance.title.replace(' ', '_')}")
    playlist_dir = os.path.join(base_dir, "playlist")
    key_dir = os.path.join(base_dir, "keys")

    os.makedirs(playlist_dir, exist_ok=True)
    os.makedirs(key_dir, exist_ok=True)

    # --- 🎬 Handle playlist file (.m3u8) ---
    if instance.hls_playlist and os.path.exists(instance.hls_playlist.path):
        dest = os.path.join(playlist_dir, os.path.basename(instance.hls_playlist.name))

        # ✅ Only move if it's not already in the right place
        if instance.hls_playlist.path != dest:
            # If a previous playlist exists, delete it first
            old_files = [f for f in os.listdir(playlist_dir) if f.endswith(".m3u8")]
            for old_file in old_files:
                try:
                    os.remove(os.path.join(playlist_dir, old_file))
                except Exception as e:
                    print(f"⚠️ Could not delete old playlist {old_file}: {e}")

            # Move the new one
            shutil.move(instance.hls_playlist.path, dest)

            # Save the new relative path
            relative_dest = os.path.relpath(dest, settings.MEDIA_ROOT).replace("\\", "/")
            instance.hls_playlist.name = relative_dest
            instance.save(update_fields=["hls_playlist"])

    # --- 🔐 Handle encryption key file ---
    if instance.encryption_key and os.path.exists(instance.encryption_key.path):
        dest = os.path.join(key_dir, os.path.basename(instance.encryption_key.name))

        # ✅ Only move if not already there
        if instance.encryption_key.path != dest:
            # If an old key exists, delete it first
            old_files = [f for f in os.listdir(key_dir) if f.endswith(".key")]
            for old_file in old_files:
                try:
                    os.remove(os.path.join(key_dir, old_file))
                except Exception as e:
                    print(f"⚠️ Could not delete old key {old_file}: {e}")

            # Move the new key
            shutil.move(instance.encryption_key.path, dest)

            # Save the relative path
            relative_dest = os.path.relpath(dest, settings.MEDIA_ROOT).replace("\\", "/")
            instance.encryption_key.name = relative_dest
            instance.save(update_fields=["encryption_key"])
