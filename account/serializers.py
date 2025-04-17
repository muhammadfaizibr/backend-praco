from rest_framework import serializers
from account.models import User
from backend_praco.utils import send_email
from django.contrib.auth.hashers import check_password

class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "company_name", "password"]
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 8, 'max_length': 20}
        }

    def validate_email(self, value):
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255, required=True)
    password = serializers.CharField(max_length=255, write_only=True, required=True)

    def validate_email(self, value):
        return value.lower()

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "company_name"]
        extra_kwargs = {
            'email': {'read_only': True},  # Prevent updating email
            'id': {'read_only': True},     # Prevent updating ID
        }

    def get_fields(self):
        fields = super().get_fields()
        # For PATCH, allow only updatable fields
        if self.context.get('request') and self.context['request'].method == 'PATCH':
            return {
                key: field for key, field in fields.items()
                if key in ['first_name', 'last_name', 'company_name']
            }
        return fields


class EmailAuthenticationSerializer(serializers.Serializer):
    email = serializers.EmailField(
        max_length=255,
        required=True,
        error_messages={'required': 'Email address is required.', 'blank': 'Email address cannot be blank.'}
    )

    def validate(self, attrs):
        email = attrs.get('email').lower()
        # code = self.context.get('code')

        if not User.objects.filter(email=email).exists():
            raise serializers.ValidationError('No account found with this email address.')
        
        return attrs

class UserResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(
        max_length=255,
        required=True,
        error_messages={'required': 'Email address is required.', 'blank': 'Email address cannot be blank.'}
    )
    new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'New password is required.', 'blank': 'New password cannot be blank.'}
    )
    confirm_new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'Confirm password is required.', 'blank': 'Confirm password cannot be blank.'}
    )

    def validate_email(self, value):
        return value.lower()

    def validate(self, attrs):
        email = attrs.get('email')
        new_password = attrs.get('new_password')
        confirm_new_password = attrs.get('confirm_new_password')

        if new_password != confirm_new_password:
            raise serializers.ValidationError("New password and confirm password do not match.")

        user = User.objects.filter(email=email).first()
        if not user:
            raise serializers.ValidationError("No account found with this email address.")

        user.set_password(new_password)
        user.save()
        return attrs

class UserChangedPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        max_length=255,
        write_only=True,
        required=True,
        error_messages={'required': 'Current password is required.', 'blank': 'Current password cannot be blank.'}
    )
    new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'New password is required.', 'blank': 'New password cannot be blank.'}
    )
    confirm_new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'Confirm password is required.', 'blank': 'Confirm password cannot be blank.'}
    )

    def validate(self, attrs):
        user = self.context.get('user')
        current_password = attrs.get('current_password')
        new_password = attrs.get('new_password')
        confirm_new_password = attrs.get('confirm_new_password')

        if not check_password(current_password, user.password):
            raise serializers.ValidationError("Current password is incorrect.")

        if new_password != confirm_new_password:
            raise serializers.ValidationError("New password and confirm password do not match.")

        if check_password(new_password, user.password):
            raise serializers.ValidationError("New password cannot be the same as the current password.")

        user.set_password(new_password)
        user.save()
        return attrs