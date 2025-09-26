from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

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
        print(f"⚠️ Could not send real-time notification: {e}")
