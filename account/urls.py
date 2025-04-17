from django.urls import path
from account.views import (
    UserRegistrationView,
    UserLoginView,
    UserProfileView,
    EmailAuthenticationView,
    UserResetPasswordView,
    UserUpdatePasswordView,
)
from rest_framework_simplejwt.views import (
    TokenVerifyView,
    TokenRefreshView,
)

urlpatterns = [
    # Authentication endpoints
    path('register/', UserRegistrationView.as_view(), name='user-register'),
    path('login/', UserLoginView.as_view(), name='user-login'),
    path('token/verify/', TokenVerifyView.as_view(), name='token-verify'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # User profile management
    path('profile/', UserProfileView.as_view(), name='user-profile'),

    # Password management
    path('email-authentication/', EmailAuthenticationView.as_view(), name='email-authentication'),
    path('reset-password/', UserResetPasswordView.as_view(), name='reset-password'),
    path('update-password/', UserUpdatePasswordView.as_view(), name='update-password'),
]