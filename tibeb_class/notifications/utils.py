from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
import json

import firebase_admin
from firebase_admin import credentials, messaging

def send_realtime_notification(user_id, message):
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "send_notification",  # matches the handler name in consumer
                "message": message,
            },
        )
    except Exception as e:
        print(f" Could not send real-time notification: {e}")


def _initialize_firebase():
    if firebase_admin._apps:
        return True

    credentials_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", "").strip()
    credentials_json = getattr(settings, "FIREBASE_CREDENTIALS_JSON", "").strip()

    if not credentials_path and not credentials_json:
        return False

    try:
        if credentials_json:
            cert_dict = json.loads(credentials_json)
            cred = credentials.Certificate(cert_dict)
        else:
            cred = credentials.Certificate(credentials_path)

        firebase_admin.initialize_app(cred)
        return True
    except Exception as e:
        print(f" Firebase init failed: {e}")
        return False


def send_firebase_notification(user, title, body, data=None):
    token = getattr(user, "fcm_token", None)
    if not token:
        return False

    if not _initialize_firebase():
        return False

    payload_data = {}
    if data:
        payload_data = {str(k): str(v) for k, v in data.items() if v is not None}

    message = messaging.Message(
        token=token,
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=payload_data,
    )

    try:
        messaging.send(message)
        return True
    except Exception as e:
        print(f" FCM send failed for user {user.id}: {e}")
        return False
