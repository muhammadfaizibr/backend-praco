from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from account.serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserResetPasswordSerializer,
    UserChangedPasswordSerializer,
    EmailAuthenticationSerializer,
)
from account.auth import UserBackend
from backend_praco.renderers import CustomRenderer
from backend_praco.utils import get_tokens_for_user, send_email
from account.models import User
import random

class UserRegistrationView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            token = get_tokens_for_user(user)
            return Response(
                {"message": "Account created successfully.", "token": token},
                status=status.HTTP_201_CREATED
            )

class UserLoginView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = UserBackend.authenticate(
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
            )
            if user:
                token = get_tokens_for_user(user)
                return Response(
                    {"message": "Login successful.", "token": token},
                    status=status.HTTP_200_OK
                )
            return Response(
                {"errors": {"non_field_errors": ["Invalid email or password"]}},
                status=status.HTTP_400_BAD_REQUEST
            )

class UserProfileView(RetrieveUpdateDestroyAPIView):
    renderer_classes = [CustomRenderer]
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        serializer.save()
        return Response({"message": "Profile updated successfully."}, status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        instance.delete()
        return Response({"message": "Account deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

class EmailAuthenticationView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = EmailAuthenticationSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            email = serializer.validated_data['email']
            exists = serializer.validated_data['exists']
            authentication_type = serializer.validated_data['authentication_type']
            return Response(
                {
                    "success": True,
                    "exists": exists,
                    "message": f"Verification code sent to {email}. Check inbox and spam folder.",
                    "authentication_type": authentication_type
                },
                status=status.HTTP_200_OK
            )
        return Response(
            {
                "success": False,
                "exists": False,
                "message": "Invalid verification data."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

class UserResetPasswordView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = UserResetPasswordSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            return Response(
                {"message": "Password reset successfully."},
                status=status.HTTP_200_OK
            )

class UserUpdatePasswordView(APIView):
    renderer_classes = [CustomRenderer]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserChangedPasswordSerializer(data=request.data, context={'user': request.user})
        if serializer.is_valid(raise_exception=True):
            return Response(
                {"message": "Password updated successfully."},
                status=status.HTTP_200_OK
            )

class TestEmailView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        email = request.data.get('email', 'test@example.com')
        success = send_email(
            subject="Test Email",
            body="This is a test email from Django.",
            receiver=email
        )
        if success:
            return Response(
                {"message": f"Test email sent to {email}"},
                status=status.HTTP_200_OK
            )
        return Response(
            {"message": "Failed to send test email"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )