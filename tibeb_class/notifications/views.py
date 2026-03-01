# notifications/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from tibeb_class.permissions import IsVerified
from .models import Notification
from .serializers import NotificationSerializer


class NotificationPagination(PageNumberPagination):
    page_size = 10  # default per page
    page_size_query_param = "page_size"
    max_page_size = 100


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsVerified])
def get_user_notifications(request):
    """
    Get paginated notifications for the logged-in user.
    """
    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

    paginator = NotificationPagination()
    paginated_notifications = paginator.paginate_queryset(notifications, request)

    serializer = NotificationSerializer(paginated_notifications, many=True)
    response = paginator.get_paginated_response(serializer.data)
    response.data["unread_count"] = unread_count
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
def mark_notification_read(request, pk):
    """
    Mark one notification as read by ID.
    """
    try:
        notification = Notification.objects.get(pk=pk, user=request.user)
    except Notification.DoesNotExist:
        return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)

    if notification.is_read:
        return Response({"detail": "Notification already read."}, status=status.HTTP_200_OK)

    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return Response({"detail": "Notification marked as read."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsVerified])
def mark_all_notifications_read(request):
    """
    Mark all notifications for the logged-in user as read.
    """
    updated_count = (
        Notification.objects.filter(user=request.user, is_read=False)
        .update(is_read=True)
    )
    return Response(
        {"detail": f"{updated_count} notifications marked as read."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsVerified])
def save_fcm_token(request):
    token = request.data.get("fcm_token")
    if token is None:
        return Response(
            {"detail": "fcm_token is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    token = str(token).strip()
    request.user.fcm_token = token if token else None
    request.user.save(update_fields=["fcm_token"])
    return Response({"detail": "FCM token updated."}, status=status.HTTP_200_OK)
