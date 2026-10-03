from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """DRF token authentication with a server-enforced absolute lifetime."""

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            token = model.objects.select_related("user").get(key=key)
        except model.DoesNotExist as exc:
            raise AuthenticationFailed("无效的登录凭据") from exc

        if not token.user.is_active:
            raise AuthenticationFailed("用户已停用")

        expires_at = token.created + timedelta(seconds=settings.AUTH_TOKEN_TTL_SECONDS)
        if timezone.now() >= expires_at:
            token.delete()
            raise AuthenticationFailed("登录状态已过期，请重新登录")
        return token.user, token

