import os
import mimetypes
import tempfile
import time
from django.core.files.storage import Storage
from django.conf import settings
from django.core.files.base import ContentFile
from obs import ObsClient


class TeleCloudOBSStorage(Storage):
    """
    Production-grade Huawei OBS storage for Django.
    Optimized for large files, streaming media, and admin uploads.
    Includes retry logic for unstable connections.
    """

    def __init__(self, *args, **kwargs):
        self.bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "tibebclass")
        self.endpoint = getattr(settings, "AWS_S3_ENDPOINT_URL", "").replace("https://", "")
        self.access_key = settings.AWS_ACCESS_KEY_ID
        self.secret_key = settings.AWS_SECRET_ACCESS_KEY

        # OBS client
        self.client = ObsClient(
            access_key_id=self.access_key,
            secret_access_key=self.secret_key,
            server=f"https://{self.endpoint}",
        )

        # Threshold for multipart uploads (20 MB)
        self.large_file_threshold = 20 * 1024 * 1024
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 2  # seconds between retries

    def _clean_name(self, name: str) -> str:
        return name.replace("\\", "/")

    def _get_content_type(self, name):
        content_type, _ = mimetypes.guess_type(name)
        return content_type or "application/octet-stream"

    # === Core save() ===
    def _save(self, name, content):
        key = self._clean_name(name)
        print(f"Saving to TeleCloud OBS: {key}")

        if hasattr(content, "open"):
            try:
                content.open("rb")
            except Exception:
                pass

        try:
            size = content.size
        except Exception:
            content.seek(0, os.SEEK_END)
            size = content.tell()
            content.seek(0)

        if size > self.large_file_threshold:
            return self._upload_large_file(key, content, size)
        else:
            return self._upload_small_file(key, content)

    # === Small File Upload with Retry ===
    def _upload_small_file(self, key, content):
        data = content.read()
        if isinstance(data, memoryview):
            data = data.tobytes()

        headers = {
            "Content-Type": self._get_content_type(key),
            "Cache-Control": "max-age=86400",
            "Content-Disposition": "inline",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.client.putContent(self.bucket_name, key, data, headers=headers)
                if resp.status < 300:
                    print(f"Small file uploaded: {key} ({len(data)} bytes)")
                    return key
                raise Exception(f"Status {resp.status}: {resp.errorMessage}")
            except Exception as e:
                print(f"Upload attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise Exception(f"OBS small file upload failed after {self.max_retries} retries: {e}")

    # === Large File Upload with Retry ===
    def _upload_large_file(self, key, content, size):
        import math
        from obs import model

        # Ensure real file path
        if hasattr(content, "temporary_file_path"):
            local_path = content.temporary_file_path()
        else:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                for chunk in content.chunks():
                    tmp.write(chunk)
                local_path = tmp.name

        content_type = self._get_content_type(key)
        part_size = 8 * 1024 * 1024  # 8 MB
        part_count = math.ceil(size / part_size)

        upload_id = None

        try:
            # 1️⃣ Initiate multipart upload
            init_resp = self.client.initiateMultipartUpload(
                bucketName=self.bucket_name,
                objectKey=key,
                contentType=content_type,
            )
            if init_resp.status >= 300:
                raise Exception(f"Failed to initiate multipart upload: {init_resp.errorMessage}")
            upload_id = init_resp.body.uploadId
            print(f"Multipart upload initiated: {upload_id}")

            parts = []
            with open(local_path, "rb") as f:
                for part_number in range(1, part_count + 1):
                    offset = (part_number - 1) * part_size
                    current_part_size = min(part_size, size - offset)
                    print(f" Uploading part {part_number}/{part_count} (offset={offset}, size={current_part_size})...")

                    # Retry each part upload
                    for attempt in range(1, self.max_retries + 1):
                        try:
                            resp = self.client.uploadPart(
                                bucketName=self.bucket_name,
                                objectKey=key,
                                partNumber=part_number,
                                uploadId=upload_id,
                                object=local_path,
                                isFile=True,
                                partSize=current_part_size,
                                offset=offset,
                            )
                            if resp.status < 300:
                                parts.append({'partNumber': part_number, 'etag': resp.body.etag})
                                break
                            raise Exception(f"Status {resp.status}: {resp.errorMessage}")
                        except Exception as e:
                            print(f"Part {part_number} attempt {attempt}/{self.max_retries} failed: {e}")
                            if attempt < self.max_retries:
                                time.sleep(self.retry_delay)
                            else:
                                raise Exception(f"Failed to upload part {part_number} after {self.max_retries} retries")

            # 3️⃣ Complete multipart upload
            print("Completing multipart upload...")
            complete_parts = [model.CompletePart(partNum=p['partNumber'], etag=p['etag']) for p in parts]
            complete_request = model.CompleteMultipartUploadRequest(complete_parts)

            for attempt in range(1, self.max_retries + 1):
                try:
                    comp_resp = self.client.completeMultipartUpload(
                        bucketName=self.bucket_name,
                        objectKey=key,
                        uploadId=upload_id,
                        completeMultipartUploadRequest=complete_request,
                    )
                    if comp_resp.status < 300:
                        print(f"Large file successfully uploaded to OBS: {key}")
                        break
                    raise Exception(f"Status {comp_resp.status}: {comp_resp.errorMessage}")
                except Exception as e:
                    print(f"Completion attempt {attempt}/{self.max_retries} failed: {e}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay)
                    else:
                        raise Exception(f"Failed to complete upload after {self.max_retries} retries: {e}")

        except Exception as e:
            # Abort multipart upload if any step fails
            if upload_id:
                try:
                    self.client.abortMultipartUpload(
                        bucketName=self.bucket_name,
                        objectKey=key,
                        uploadId=upload_id,
                    )
                    print("Aborted multipart upload due to error.")
                except Exception:
                    pass
            raise Exception(f"OBS multipart upload error: {e}")

        finally:
            if not hasattr(content, "temporary_file_path"):
                try:
                    os.remove(local_path)
                except Exception:
                    pass

        return key

    # === Utility Methods ===
    def exists(self, name):
        key = self._clean_name(name)
        resp = self.client.getObjectMetadata(self.bucket_name, key)
        return resp.status < 300

    def url(self, name):
        key = self._clean_name(name)
        resp = self.client.createSignedUrl(
            method="GET",
            bucketName=self.bucket_name,
            objectKey=key,
            expires=3600,
        )
        return resp.signedUrl

    def open(self, name, mode="rb"):
        key = self._clean_name(name)
        resp = self.client.getObject(self.bucket_name, key, loadStreamInMemory=True)
        if resp.status >= 300:
            raise FileNotFoundError(f"OBS file not found: {name}")
        return ContentFile(resp.body.buffer)

    def delete(self, name):
        key = self._clean_name(name)
        resp = self.client.deleteObject(self.bucket_name, key)
        if resp.status < 300:
            print(f"Deleted {key}")
        else:
            print(f"Delete failed for {key}: {resp.errorMessage}")
