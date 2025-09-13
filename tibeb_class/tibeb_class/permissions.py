from rest_framework.permissions import BasePermission

class IsVerified(BasePermission):
    """
    Allows access only to verified users.
    """
    message = "Your account is not verified. Please verify your email or phone."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_verified)
