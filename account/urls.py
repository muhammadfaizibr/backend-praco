from django.urls import path
from account.views import (
    UserRegistrationView,
    UserLoginView, 
    UserProfileView, 
    UserUpdatePasswordRequestView, 
    SendVerificationEmailView, 
    ForgetPasswordView, 
    UserResetPasswordView, 
    UserUpdatePasswordView, 
    DestroyAccountView
)

from rest_framework_simplejwt.views import (
    TokenVerifyView,
    TokenRefreshView,
)

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='user-register'),
    path('login/', UserLoginView.as_view(), name='user-login'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('update-password-request/', UserUpdatePasswordRequestView.as_view(), name='update-password-request'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('verify-email/', SendVerificationEmailView.as_view()),
    path('forget-password/', ForgetPasswordView.as_view()),
    path('reset-password/', UserResetPasswordView.as_view()),
    path('update-password/', UserUpdatePasswordView.as_view()),
    path('delete-account/<int:pk>/', DestroyAccountView.as_view(), name='delete-department-alignment'),
]
