from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import DestroyAPIView
from account.serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserPasswordChangeRequestSerializer,
    UserResetPasswordSerializer,
    UserChangedPasswordSerializer,
    SendVerificationEmailSerializer,
    ForgetPasswordSerializer
)
from account.auth import UserBackend
from backend_praco.renderers import CustomRenderer
from backend_praco.utils import send_email, get_tokens_for_user
from account.models import User
import os
import datetime
import random

class UserRegistrationView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            token = get_tokens_for_user(user)
            send_email(
                subject="Account Created",
                message=f"A new account created at {datetime.datetime.now()}",
                recipient=serializer.data.get("email")
            )
            return Response(
                {"message": "Your account has been successfully created.", "token": token},
                status=status.HTTP_201_CREATED
            )

class UserLoginView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = UserBackend.authenticate(
                email=serializer.data.get("email"),
                password=serializer.data.get("password"),
            )
            if user:
                token = get_tokens_for_user(user)
                return Response(
                    {"message": "You have successfully logged in.", "token": token},
                    status=status.HTTP_200_OK
                )
            return Response(
                {"errors": {"non_field_errors": ["Invalid email or password"]}},
                status=status.HTTP_400_BAD_REQUEST
            )

class UserProfileView(APIView):
    renderer_classes = [CustomRenderer]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

class DestroyAccountView(DestroyAPIView):
    renderer_classes = [CustomRenderer]
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer

class UserUpdatePasswordRequestView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = UserPasswordChangeRequestSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            email = serializer.data.get("email")
            reason = serializer.data.get("reason")
            send_email(
                subject="Password Change Request",
                message=f"Password change request by {email}\nReason: {reason}\nTime: {datetime.datetime.now()}",
                recipient=os.environ.get("EMAIL_USER")
            )
            return Response(
                {"message": "Your password change request has been submitted. You will be notified soon."},
                status=status.HTTP_200_OK
            )

class SendVerificationEmailView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        code = random.randint(1000, 9999)
        serializer = SendVerificationEmailSerializer(data=request.data, context={'code': code})
        if serializer.is_valid(raise_exception=True):
            email = request.data['email'].lower()
            return Response(
                {'message': f"A verification code has been sent to {email}. Please check your inbox and spam folder.", 'code': code},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ForgetPasswordView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        code = random.randint(1000, 9999)
        serializer = ForgetPasswordSerializer(data=request.data, context={'code': code})
        if serializer.is_valid(raise_exception=True):
            email = request.data['email'].lower()
            return Response(
                {'message': f"A verification code has been sent to {email}. Please check your inbox and spam folder.", 'code': code},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserResetPasswordView(APIView):
    renderer_classes = [CustomRenderer]

    def post(self, request):
        serializer = UserResetPasswordSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            return Response(
                {'message': "Your password has been successfully reset."},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserUpdatePasswordView(APIView):
    renderer_classes = [CustomRenderer]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserChangedPasswordSerializer(data=request.data, context={'user': request.user})
        if serializer.is_valid(raise_exception=True):
            return Response(
                {'message': "Your password has been successfully updated."},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)