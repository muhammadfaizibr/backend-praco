from django.contrib.auth.backends import ModelBackend
from account.models import User

class UserBackend(ModelBackend):
    def authenticate(email=None, password=None):
        try:
            user = User.objects.get(email=email)
            print('user', user)
            if user.check_password(password):
                return user
            
        except User.DoesNotExist:
            return None
        
    def get_user(user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None