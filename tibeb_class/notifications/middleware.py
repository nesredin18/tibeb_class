from urllib.parse import parse_qs
from channels.db import database_sync_to_async


@database_sync_to_async
def get_user_from_token(token_key):
    try:
        # Import Django-related modules *inside* the function
        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model
        User = get_user_model()

        access_token = AccessToken(token_key)
        user = User.objects.get(id=access_token['user_id'])
        return user
    except Exception as e:
        print(f"[JWTAuthMiddleware] Token validation failed: {e}")
        from django.contrib.auth.models import AnonymousUser
        return AnonymousUser()


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        from urllib.parse import parse_qs
        from django.contrib.auth.models import AnonymousUser
        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model
        from channels.db import database_sync_to_async

        User = get_user_model()

        @database_sync_to_async
        def get_user(token):
            try:
                token_obj = AccessToken(token)
                return User.objects.get(id=token_obj["user_id"])
            except Exception:
                return AnonymousUser()

        query = parse_qs(scope["query_string"].decode())
        token = query.get("token", [None])[0]
        scope["user"] = await get_user(token) if token else AnonymousUser()

        inner = self.inner
        return await inner(scope, receive, send)



class JWTAuthMiddlewareInstance:
    def __init__(self, scope, middleware):
        self.scope = dict(scope)
        self.middleware = middleware

    async def __call__(self, receive, send):
        from django.contrib.auth.models import AnonymousUser  # safe to import here
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        if token:
            self.scope["user"] = await get_user_from_token(token)
        else:
            self.scope["user"] = AnonymousUser()

        inner = self.middleware.inner
        return await inner(self.scope, receive, send)
