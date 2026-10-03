from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .api_serializers import LoginSerializer, RegisterSerializer


def user_data(user):
    return {
        "id": user.id,
        "username": user.get_username(),
        "is_staff": user.is_staff,
    }


def token_data(token):
    expires_at = token.created + timedelta(seconds=settings.AUTH_TOKEN_TTL_SECONDS)
    return {
        "token": token.key,
        "expires_at": expires_at.isoformat(),
        "expires_in": settings.AUTH_TOKEN_TTL_SECONDS,
    }


def issue_token(user):
    token, created = Token.objects.get_or_create(user=user)
    if not created:
        Token.objects.filter(pk=token.pk).update(
            key=Token.generate_key(),
            created=timezone.now(),
        )
        token = Token.objects.get(user=user)
    return token


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token = issue_token(user)
        return Response({**token_data(token), "user": user_data(user)})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token = Token.objects.create(user=user)
        return Response({**token_data(token), "user": user_data(user)}, status=201)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_data(request.user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=204)
