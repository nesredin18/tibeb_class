import os
import uuid

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage, default_storage
from django.utils.text import get_valid_filename


LOCAL_RECEIPT_PREFIX = "local_receipts"
SUBSCRIPTION_LOCAL_RECEIPT_DIR = f"{LOCAL_RECEIPT_PREFIX}/subscription_payment_receipts"
SUBSCRIPTION_REMOTE_RECEIPT_DIR = "subscription_payment_receipts"


def is_local_receipt_name(name):
    return bool(name) and str(name).replace("\\", "/").startswith(f"{LOCAL_RECEIPT_PREFIX}/")


def get_local_receipt_storage():
    return FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)


def _safe_extension(filename):
    _, ext = os.path.splitext(filename or "")
    ext = get_valid_filename(ext.lower())[:16]
    return ext if ext.startswith(".") else ""


def save_subscription_receipt_locally(uploaded_file):
    storage = get_local_receipt_storage()
    extension = _safe_extension(getattr(uploaded_file, "name", ""))
    name = f"{SUBSCRIPTION_LOCAL_RECEIPT_DIR}/{uuid.uuid4().hex}{extension}"
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    saved_name = storage.save(name, uploaded_file)
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return saved_name


def build_receipt_url(name):
    if not name:
        return None
    clean_name = str(name).replace("\\", "/")
    if is_local_receipt_name(clean_name):
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        url = f"{media_url.rstrip('/')}/{clean_name.lstrip('/')}"
        base = (getattr(settings, "BACKEND_URL", "") or "").rstrip("/")
        return f"{base}{url}" if base and url.startswith("/") else url
    return default_storage.url(clean_name)


def move_subscription_receipt_to_default_storage(payment):
    local_name = getattr(payment.receipt_file, "name", "")
    if not is_local_receipt_name(local_name):
        return None

    local_storage = get_local_receipt_storage()
    if not local_storage.exists(local_name):
        raise FileNotFoundError(f"Local receipt file not found: {local_name}")

    extension = _safe_extension(local_name)
    remote_name = f"{SUBSCRIPTION_REMOTE_RECEIPT_DIR}/{uuid.uuid4().hex}{extension}"
    with local_storage.open(local_name, "rb") as handle:
        saved_remote_name = default_storage.save(remote_name, File(handle))

    payment.receipt_file.name = saved_remote_name
    payment.save(update_fields=["receipt_file"])
    local_storage.delete(local_name)
    return saved_remote_name
