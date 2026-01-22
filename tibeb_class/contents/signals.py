import zipfile
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from tibeb_class import settings
from .models import Video
from .models import Book
import fitz
from django.db.models.signals import m2m_changed
from .models import Question
import os, json, subprocess
from datetime import timedelta



import tempfile
import requests
@receiver(pre_save, sender=Book)
def remember_old_pdf_file(sender, instance, **kwargs):
    """
    Store the old PDF file name before save, so we can detect changes after saving.
    """
    if not instance.pk:
        instance._old_pdf_name = None
    else:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_pdf_name = old.pdf_file.name if old.pdf_file else None
        except sender.DoesNotExist:
            instance._old_pdf_name = None


# @receiver(post_save, sender=Book)
# def extract_pdf_page_count_remote(sender, instance, **kwargs):
#     """
#     Extract and update total PDF pages when a PDF is created or replaced (even if remote).
#     """
#     if not instance.pdf_file:
#         print("No PDF file attached — skipping page count.")
#         return
#
#     try:
#         new_name = instance.pdf_file.name
#         old_name = getattr(instance, "_old_pdf_name", None)
#         file_changed = new_name != old_name
#
#         # Skip if unchanged and total_pages already exists
#         if not file_changed and instance.total_pages:
#             print(f"Skipping {instance.name} — same PDF ({instance.total_pages} pages).")
#             return
#
#         print(f"Fetching PDF from: {instance.pdf_file.url}")
#
#         # Download temporarily
#         with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp:
#             response = requests.get(instance.pdf_file.url, timeout=30)
#             response.raise_for_status()
#             tmp.write(response.content)
#             tmp.flush()
#
#             with fitz.open(tmp.name) as doc:
#                 total_pages = doc.page_count
#                 print(f"Extracted {total_pages} pages for {instance.name}")
#
#                 # Safe update (no recursion)
#                 sender.objects.filter(pk=instance.pk).update(total_pages=total_pages)
#
#     except Exception as e:
#         print(f"Failed to extract PDF page count for {instance.name}: {e}")


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
import tempfile
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from obs import ObsClient
from .models import Video


import os, zipfile, tempfile, json, subprocess, time
from datetime import timedelta
from urllib.request import urlretrieve
from django.conf import settings
from obs import ObsClient
from .models import Video

import os, zipfile, tempfile, json, subprocess, time, re
from datetime import timedelta
from urllib.request import urlretrieve
from django.conf import settings
from obs import ObsClient
from .models import Video


def get_obs_client():
    """Return initialized Huawei OBS client."""
    print(" Initializing Huawei TeleCloud OBS client...")
    return ObsClient(
        access_key_id=settings.AWS_ACCESS_KEY_ID,
        secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        server=settings.AWS_S3_ENDPOINT_URL,
    )


import os, zipfile, tempfile, json, subprocess, time, re
from datetime import timedelta
from urllib.request import urlretrieve
from django.conf import settings
from obs import ObsClient


def get_obs_client():
    """Return initialized Huawei OBS client."""
    print("Initializing Huawei TeleCloud OBS client...")
    return ObsClient(
        access_key_id=settings.AWS_ACCESS_KEY_ID,
        secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        server=settings.AWS_S3_ENDPOINT_URL,
    )


def _extract_hls_zip_from_local(instance):
    """Extract locally stored HLS ZIP → upload segments → download playlist if needed →
       rewrite URLs → compute duration with ffprobe."""
    print(f" Starting extraction for video: {instance.title} (ID={instance.id})")

    # 🛑 Prevent recursion (avoid infinite signal loops)
    if getattr(instance, "_skip_extraction", False):
        print("⏭Skipping extraction (internal save).")
        return

    if not instance.segments_zip:
        print(" No ZIP file attached — skipping extraction.")
        return

    local_zip_path = instance.segments_zip.path
    if not os.path.exists(local_zip_path):
        print(f" ZIP file not found at: {local_zip_path}")
        return

    obs = get_obs_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    base_prefix = f"videos/hls/{instance.id}_{instance.title.replace(' ', '_')}"
    segments_prefix = f"{base_prefix}/segments/"

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f" Extracting ZIP into: {tmpdir}")

        # --- Extract ZIP contents ---
        try:
            with zipfile.ZipFile(local_zip_path, "r") as zip_ref:
                file_list = zip_ref.namelist()
                print(f" ZIP contains {len(file_list)} files.")
                zip_ref.extractall(tmpdir)
        except zipfile.BadZipFile:
            print(" Invalid ZIP file.")
            return
        except Exception as e:
            print(f" Error extracting ZIP: {e}")
            return

        # --- Clean old OBS segments ---
        print(f" Cleaning old OBS segments under: {segments_prefix}")
        try:
            resp = obs.listObjects(bucket, prefix=segments_prefix)
            if hasattr(resp, "body") and getattr(resp.body, "contents", None):
                for obj in resp.body.contents:
                    print(f"    Deleting old object: {obj.key}")
                    obs.deleteObject(bucket, obj.key)
            else:
                print(" No old segments found.")
        except Exception as e:
            print(f" Failed cleaning OBS: {e}")

        # --- Upload extracted files ---
        MAX_RETRIES, RETRY_DELAY = 3, 2
        print(" Uploading extracted files to TeleCloud OBS...")
        uploaded_count = 0

        for root, _, files in os.walk(tmpdir):
            for f in files:
                full_path = os.path.join(root, f)
                ext = os.path.splitext(f)[1].lower()

                # Type mapping
                if ext == ".ts":
                    key = f"{base_prefix}/segments/{f}"
                    content_type = "video/MP2T"
                elif ext == ".m3u8":
                    key = f"{base_prefix}/playlist/{f}"
                    content_type = "application/vnd.apple.mpegurl"
                elif ext == ".key":
                    key = f"{base_prefix}/keys/{f}"
                    content_type = "application/octet-stream"
                elif ext in (".jpg", ".jpeg", ".png"):
                    key = f"{base_prefix}/images/{f}"
                    content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
                elif ext == ".pdf":
                    key = f"{base_prefix}/docs/{f}"
                    content_type = "application/pdf"
                else:
                    key = f"{base_prefix}/misc/{f}"
                    content_type = "application/octet-stream"

                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        resp = obs.putFile(
                            bucket, key, full_path,
                            headers={
                                "Content-Type": content_type,
                                "Cache-Control": "max-age=86400",
                                "Content-Disposition": "inline",
                            },
                        )
                        if resp.status < 300:
                            uploaded_count += 1
                            print(f" Uploaded {key} ({os.path.getsize(full_path)} bytes)")
                            break
                        raise Exception(f"Status {resp.status}: {resp.errorMessage}")
                    except Exception as e:
                        print(f" Upload attempt {attempt}/{MAX_RETRIES} failed for {f}: {e}")
                        if attempt < MAX_RETRIES:
                            time.sleep(RETRY_DELAY)
                        else:
                            print(f" Upload failed permanently for {f} after {MAX_RETRIES} retries.")

        print(f" Uploaded {uploaded_count} files successfully.")

        # --- Locate or download playlist ---
        playlist_files = [f for f in os.listdir(tmpdir) if f.endswith(".m3u8")]
        playlist_path = None

        if playlist_files:
            playlist_path = os.path.join(tmpdir, playlist_files[0])
            print(f" Found local playlist in ZIP: {playlist_path}")
        elif instance.hls_playlist:
            # Download playlist from OBS via signed URL
            print(" Downloading playlist from OBS for duration analysis...")
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".m3u8") as tmp_playlist:
                    urlretrieve(instance.hls_playlist.url, tmp_playlist.name)
                    playlist_path = tmp_playlist.name
                    print(f" Downloaded playlist from OBS: {playlist_path}")
            except Exception as e:
                print(f" Failed to download playlist from OBS: {e}")

#         # --- Compute duration using rewritten playlist ---
#         if playlist_path and os.path.exists(playlist_path):
#             try:
#                 print(" Rewriting playlist with signed URLs for ffprobe access...")
#                 playlist_text = open(playlist_path, "r", encoding="utf-8").read()
#
#                 # 1️⃣ Replace encryption key URI with signed URL
#                 if 'EXT-X-KEY' in playlist_text and instance.encryption_key:
#                     key_url = instance.encryption_key.url  # signed URL from storage
#                     playlist_text = re.sub(r'URI=\".*?\"', f'URI="{key_url}"', playlist_text)
#
#                 # 2️⃣ Replace segment file names with signed URLs
#                 segment_dir = f"videos/hls/{instance.id}_{instance.title.replace(' ', '_')}/segments/"
#                 segment_resp = obs.listObjects(bucket, prefix=segment_dir)
#                 if hasattr(segment_resp, "body") and getattr(segment_resp.body, "contents", None):
#                     for obj in segment_resp.body.contents:
#                         if obj.key.endswith(".ts"):
#                             seg_name = os.path.basename(obj.key)
#                             seg_url = obs.createSignedUrl(
#                                 method="GET",
#                                 bucketName=bucket,
#                                 objectKey=obj.key,
#                                 expires=600
#                             ).signedUrl
#                             playlist_text = playlist_text.replace(seg_name, seg_url)
#
#                 # Write modified playlist for ffprobe
#                 rewritten_path = playlist_path.replace(".m3u8", "_rewritten.m3u8")
#                 with open(rewritten_path, "w", encoding="utf-8") as f:
#                     f.write(playlist_text)
#
#                 # Run ffprobe
#                 print(" Running ffprobe on rewritten playlist...")
#                 result = subprocess.run(
#                     [
#                         "ffprobe",
#                         "-v", "error",
#                         "-allowed_extensions", "ALL",
#                         "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
#                         "-show_entries", "format=duration",
#                         "-of", "json",
#                         rewritten_path,
#                     ],
#                     stdout=subprocess.PIPE,
#                     stderr=subprocess.PIPE,
#                     text=True,
#                     check=True,
#                 )
#
#                 info = json.loads(result.stdout or "{}")
#                 total_seconds = float(info.get("format", {}).get("duration", 0))
#                 if total_seconds > 0:
#                     duration = timedelta(seconds=int(total_seconds))
#                     instance.duration = duration
#                     instance._skip_extraction = True  # 🧠 prevent infinite signal loop
#                     instance.save(update_fields=["duration"])
#                     instance._skip_extraction = False
#                     print(f" Duration extracted: {duration}")
#                 else:
#                     print(" Duration could not be determined (empty result).")
#
#             except subprocess.CalledProcessError as e:
#                 print(f" ffprobe failed: {e.stderr}")
#             except Exception as e:
#                 print(f" Duration extraction error: {e}")
#             finally:
#                 try:
#                     os.remove(playlist_path)
#                     if 'rewritten_path' in locals() and os.path.exists(rewritten_path):
#                         os.remove(rewritten_path)
#                 except Exception:
#                     pass
#         else:
#             print(" No playlist available for duration extraction.")

    # --- Cleanup local ZIP ---
    try:
        os.remove(local_zip_path)
        instance.segments_zip.delete(save=False)
        instance.segments_zip = None
        instance.save(update_fields=["segments_zip"])
        print(" Local ZIP deleted and DB field cleared.")
    except Exception as e:
        print(f" Cleanup error: {e}")

    print(f" Extraction completed successfully for {instance.title}\n")


# ====================================================
# 2️⃣ Signal trigger – runs after DB commit
# ====================================================
@receiver(post_save, sender=Video)
def extract_hls_files(sender, instance, created, **kwargs):
    """Run extraction after ZIP file is saved locally."""
    print(f" [Signal] Extract HLS files for Video ID={instance.id}, Title={instance.title}")
    transaction.on_commit(lambda: _extract_hls_zip_from_local(instance))


# ====================================================
# 3️⃣ Move playlist (.m3u8) & key to proper TeleCloud path
# ====================================================
@receiver(post_save, sender=Video)
def move_video_files(sender, instance, created, **kwargs):
    """Move HLS playlist and encryption key to final per-video folders."""
    print(f" [Signal] move_video_files for Video ID={instance.id}, Title={instance.title}")

    if not instance.id:
        print(" Instance has no ID — skipping move.")
        return

    obs = get_obs_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    base_prefix = f"videos/hls/{instance.id}_{instance.title.replace(' ', '_')}"

    # 🎬 Playlist
    if instance.hls_playlist:
        old_key = instance.hls_playlist.name
        new_key = f"{base_prefix}/playlist/{os.path.basename(old_key)}"
        if old_key != new_key:
            try:
                print(f" Moving playlist: {old_key} → {new_key}")
                obs.copyObject(bucket, old_key, bucket, new_key)
                obs.deleteObject(bucket, old_key)
                instance.hls_playlist.name = new_key
                instance.save(update_fields=["hls_playlist"])
                print(" Playlist moved successfully.")
            except Exception as e:
                print(f" Playlist move failed: {e}")

    # 🔐 Key
    if instance.encryption_key:
        old_key = instance.encryption_key.name
        new_key = f"{base_prefix}/keys/{os.path.basename(old_key)}"
        if old_key != new_key:
            try:
                print(f" Moving key: {old_key} → {new_key}")
                obs.copyObject(bucket, old_key, bucket, new_key)
                obs.deleteObject(bucket, old_key)
                instance.encryption_key.name = new_key
                instance.save(update_fields=["encryption_key"])
                print(" Key moved successfully.")
            except Exception as e:
                print(f" Key move failed: {e}")

    print(f" File organization completed for Video ID={instance.id}\n")
